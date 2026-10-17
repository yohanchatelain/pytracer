"""Reproduction tests for Subsystem 2: Data Storage & Serialization bugs.

Covers:
- BUG-STORE-001: payload_ref column omitted from events.parquet table
- BUG-STORE-002: Zarr 3 ContainsArrayError causes silent save failure and payload loss
- BUG-STORE-003: Brittle EOF truncation detection in iter_events
- BUG-STORE-004: Multiple unnamed output events overwrite each other in assemble_calls
- BUG-STORE-005: Output events with arg_name=None silently dropped from Perfetto export
- BUG-STORE-006: Zarr 2 vs 3 format incompatibilities and phantom numcodecs dependency
"""

import tempfile
import tomllib
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from pytracer.report.perfetto import _call_spans
from pytracer.storage.arrays import ArrayStore
from pytracer.storage.parquet import finalize_run
from pytracer.trace.event import SCHEMA_VERSION, NumericSummary, TraceEvent
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.writer import TraceWriter


def test_bug_store_001_parquet_payload_ref_omitted():
    """In parquet.py, _COLUMNS and _row() map payload_kind, but completely omit payload_ref.

    When external analytical engines (DuckDB, Pandas, Polars) query events.parquet,
    the column linking events to persisted array files on disk is missing.
    """
    with tempfile.TemporaryDirectory() as td:
        w = TraceWriter(td)
        w.write_event(
            TraceEvent(
                schema_version=SCHEMA_VERSION,
                run_id="r1",
                event_id=0,
                call_id=0,
                occurrence=0,
                phase="input",
                module="numpy",
                qualname="sum",
                payload_kind="array_ref",
                payload_ref="arrays/000000-input-a.npy",
            )
        )
        w.close()

        pq_path = finalize_run(td)
        tbl = pq.read_table(pq_path)
        # Expected: 'payload_ref' column exists in events.parquet schema
        # Actual on buggy code: 'payload_ref' is missing from tbl.column_names
        assert "payload_ref" in tbl.column_names, (
            f"'payload_ref' column omitted from parquet table: {tbl.column_names}"
        )


def test_bug_store_002_zarr3_contains_array_error_drops_payload():
    """Under Zarr 3.x, zarr.save() raises ContainsArrayError when writing to a path where an

    array directory already exists. ArrayStore.maybe_store() catches all Exceptions,
    drops the array payload, increments n_skipped, and returns None.
    """
    with tempfile.TemporaryDirectory() as td:
        store = ArrayStore(td, backend="zarr", mode="always")
        arr1 = np.array([1.0, 2.0])
        arr2 = np.array([3.0, 4.0])

        ref1 = store.maybe_store(1, "output", "Ret", arr1)
        assert ref1 is not None, "First array store failed"

        # Attempt to store array to the same call/phase/arg stem
        ref2 = store.maybe_store(1, "output", "Ret", arr2)
        # Expected: ref2 is successfully written without dropping payload
        # Actual on buggy code: ref2 is None and store.n_skipped is incremented to 1
        assert ref2 is not None, (
            f"Second store to existing path failed silently with n_skipped={store.n_skipped}"
        )


def test_bug_store_003_brittle_eof_truncation_detection():
    """iter_events() uses last_index = len(lines) - 1. Trailing empty newlines increase

    last_index, causing a genuinely truncated final record to fail the check
    i >= last_index - 1, raising an unhandled PytracerError instead of returning truncated=True.
    """
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "events.jsonl"
        valid = (
            b'{"schema_version":"2.0.0","run_id":"r1","event_id":0,"call_id":0,'
            b'"occurrence":0,"phase":"input","module":"m","qualname":"q"}\n'
        )
        # Partial truncated json record at the end of the file, followed by trailing blank lines
        truncated_record = b'{"schema_version":"2.0.0", "run_id":'
        p.write_bytes(valid + truncated_record + b"\n\n\n")

        # Expected: iter_events gracefully tolerates EOF truncation and returns (events, True)
        # Actual on buggy code: raises PytracerError: corrupt event at line 2
        events, was_truncated = iter_events(p)
        assert was_truncated is True, "Expected was_truncated=True"
        assert len(events) == 1, "Expected 1 valid event recovered"


def test_bug_store_004_unnamed_outputs_overwrite_in_assemble_calls():
    """In assemble_calls(): for inputs without an arg_name, names are indexed (Arg0, Arg1).

    For outputs, missing arg_names hardcode 'Ret'. If a call emits multiple outputs
    with arg_name=None, subsequent outputs overwrite rec.outputs['Ret'].
    """
    events = [
        TraceEvent(
            schema_version=SCHEMA_VERSION,
            run_id="r1",
            event_id=0,
            call_id=1,
            occurrence=0,
            phase="output",
            module="m",
            qualname="q",
            arg_name=None,
            summary=NumericSummary(dtype="float64", shape=(), size=1, mean=1.0),
        ),
        TraceEvent(
            schema_version=SCHEMA_VERSION,
            run_id="r1",
            event_id=1,
            call_id=1,
            occurrence=0,
            phase="output",
            module="m",
            qualname="q",
            arg_name=None,
            summary=NumericSummary(dtype="float64", shape=(), size=1, mean=2.0),
        ),
    ]
    calls = assemble_calls(events)
    # Expected: both outputs are preserved (e.g. 2 output records)
    # Actual on buggy code: len(calls[0].outputs) == 1 (second output overwrote first)
    assert len(calls[0].outputs) == 2, (
        f"Multiple outputs were overwritten, got only {len(calls[0].outputs)} outputs"
    )


def test_bug_store_005_perfetto_drops_unnamed_output_events():
    """In perfetto._call_spans(): elif ev.summary is not None and ev.arg_name:.

    Because output events default to arg_name=None, ev.arg_name evaluates to False,
    and output summary statistics are dropped from the exported trace span arguments.
    """
    ev = TraceEvent(
        schema_version=SCHEMA_VERSION,
        run_id="r1",
        event_id=0,
        call_id=0,
        occurrence=0,
        phase="output",
        module="numpy",
        qualname="sin",
        arg_name=None,
        summary=NumericSummary(dtype="float64", shape=(1,), size=1, mean=0.5),
        ts_ns=1000,
    )
    spans = _call_spans([ev])
    # Expected: Perfetto span args dictionary contains output summary (e.g. under 'output:Ret')
    # Actual on buggy code: spans[0]["args"] is empty {}
    assert len(spans[0]["args"]) > 0, (
        f"Output event summary was dropped from Perfetto span args: {spans[0]['args']}"
    )


def test_bug_store_006_phantom_numcodecs_dependency():
    """pyproject.toml lists numcodecs>=0.12 in optional-dependencies.arrays and all.

    However, numcodecs is never imported or used anywhere in the pytracer source code,
    adding an unnecessary and phantom dependency to user environments.
    """
    pyproject_data = tomllib.loads(Path("pyproject.toml").read_text())
    array_deps = pyproject_data["project"]["optional-dependencies"]["arrays"]
    declares_numcodecs = any("numcodecs" in dep for dep in array_deps)

    src_files = list(Path("src/pytracer").rglob("*.py"))
    uses_numcodecs = any("numcodecs" in p.read_text() for p in src_files)

    # Expected: if a dependency is declared in pyproject.toml, it should be used in the codebase
    # Actual on buggy code: declares_numcodecs is True, but uses_numcodecs is False
    assert not (declares_numcodecs and not uses_numcodecs), (
        "numcodecs is declared in pyproject.toml but never used in src/pytracer"
    )
