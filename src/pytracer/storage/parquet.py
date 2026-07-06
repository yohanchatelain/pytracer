"""Finalize a run: convert the append-safe JSONL capture to a Parquet table.

Capture never writes Parquet directly (buffered row groups + a crashing
traced program = truncated files). The JSONL capture remains the canonical
input for pytracer's own analysis; events.parquet is the interoperable
artifact for external tools (pandas, duckdb, ...).
"""

from __future__ import annotations

from pathlib import Path

from pytracer.trace.event import TraceEvent
from pytracer.trace.reader import iter_events
from pytracer.trace.writer import EVENTS_FILENAME

PARQUET_FILENAME = "events.parquet"

_COLUMNS = [
    ("schema_version", "string"),
    ("run_id", "string"),
    ("event_id", "int64"),
    ("call_id", "int64"),
    ("parent_call_id", "int64"),
    ("occurrence", "int64"),
    ("phase", "string"),
    ("module", "string"),
    ("qualname", "string"),
    ("tier", "string"),
    ("ufunc_method", "string"),
    ("arg_name", "string"),
    ("inplace", "bool"),
    ("payload_kind", "string"),
    ("source_file", "string"),
    ("source_lineno", "int64"),
    ("note", "string"),
    ("dtype", "string"),
    ("shape", "list<int64>"),
    ("size", "int64"),
    ("mean", "float64"),
    ("std", "float64"),
    ("min", "float64"),
    ("max", "float64"),
    ("l2_norm", "float64"),
    ("linf_norm", "float64"),
    ("nan_count", "int64"),
    ("inf_count", "int64"),
    ("zero_count", "int64"),
    ("subnormal_count", "int64"),
    ("fingerprint", "string"),
]


def _row(ev: TraceEvent) -> dict:
    s = ev.summary
    return {
        "schema_version": ev.schema_version,
        "run_id": ev.run_id,
        "event_id": ev.event_id,
        "call_id": ev.call_id,
        "parent_call_id": ev.parent_call_id,
        "occurrence": ev.occurrence,
        "phase": ev.phase,
        "module": ev.module,
        "qualname": ev.qualname,
        "tier": ev.tier,
        "ufunc_method": ev.ufunc_method,
        "arg_name": ev.arg_name,
        "inplace": ev.inplace,
        "payload_kind": ev.payload_kind,
        "source_file": ev.source.file if ev.source else None,
        "source_lineno": ev.source.lineno if ev.source else None,
        "note": ev.note,
        "dtype": s.dtype if s else None,
        "shape": list(s.shape) if s else None,
        "size": s.size if s else None,
        "mean": s.mean if s else None,
        "std": s.std if s else None,
        "min": s.min if s else None,
        "max": s.max if s else None,
        "l2_norm": s.l2_norm if s else None,
        "linf_norm": s.linf_norm if s else None,
        "nan_count": s.nan_count if s else None,
        "inf_count": s.inf_count if s else None,
        "zero_count": s.zero_count if s else None,
        "subnormal_count": s.subnormal_count if s else None,
        "fingerprint": s.fingerprint if s else None,
    }


def finalize_run(run_dir: str | Path) -> Path | None:
    """Write events.parquet next to events.jsonl. Returns the path, or None
    when pyarrow is unavailable or there are no events."""
    run_dir = Path(run_dir)
    events_path = run_dir / EVENTS_FILENAME
    if not events_path.is_file():
        return None
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return None

    events, _truncated = iter_events(events_path)
    rows = [_row(ev) for ev in events]

    fields = []
    for name, kind in _COLUMNS:
        if kind == "list<int64>":
            fields.append(pa.field(name, pa.list_(pa.int64())))
        elif kind == "int64":
            fields.append(pa.field(name, pa.int64()))
        elif kind == "float64":
            fields.append(pa.field(name, pa.float64()))
        elif kind == "bool":
            fields.append(pa.field(name, pa.bool_()))
        else:
            fields.append(pa.field(name, pa.string()))
    schema = pa.schema(fields)
    columns = {name: [r[name] for r in rows] for name, _ in _COLUMNS}
    table = pa.Table.from_pydict(columns, schema=schema)
    out = run_dir / PARQUET_FILENAME
    pq.write_table(table, out, compression="zstd")
    return out
