"""Direct tests for the T4 monitor, Parquet finalization, and Perfetto export."""

import json
import sys

import pytest
from test_events_io import make_event

from pytracer._errors import PytracerError
from pytracer.instrumentation.monitor import MONITOR_FILENAME, Monitor
from pytracer.report.perfetto import export_perfetto
from pytracer.storage.parquet import finalize_run
from pytracer.trace.writer import TraceWriter


@pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="needs sys.monitoring")
def test_monitor_counts_scoped_lines_and_c_calls(tmp_path):
    script = tmp_path / "prog.py"
    code_text = "total = 0\nfor i in range(5):\n    total += len(str(i))\n"
    script.write_text(code_text)

    monitor = Monitor(scope_dir=tmp_path, run_dir=tmp_path)
    monitor.start()
    if not monitor.available:  # another tool owns the profiler id
        monitor.stop()
        payload = json.loads((tmp_path / MONITOR_FILENAME).read_text())
        assert payload["available"] is False
        return
    try:
        exec(compile(code_text, str(script), "exec"), {})
    finally:
        monitor.stop()

    payload = json.loads((tmp_path / MONITOR_FILENAME).read_text())
    assert payload["available"] is True
    # the loop body line executed 5 times
    assert payload["line_counts"][f"{script}:3"] == 5
    # len/str are C callables called from scoped code
    assert any(name.endswith("len") for name in payload["c_calls"])


@pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="needs sys.monitoring")
def test_monitor_ignores_out_of_scope(tmp_path):
    monitor = Monitor(scope_dir=tmp_path / "scope", run_dir=tmp_path)
    monitor.start()
    try:
        sum(len(str(i)) for i in range(3))  # this file is out of scope
    finally:
        monitor.stop()
    payload = json.loads((tmp_path / MONITOR_FILENAME).read_text())
    assert payload["line_counts"] == {}


def test_parquet_finalize_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    writer = TraceWriter(tmp_path)
    for i in range(4):
        writer.write_event(
            make_event(event_id=i, call_id=i // 2,
                       phase="input" if i % 2 == 0 else "output", ts_ns=1000 + i)
        )
    writer.close()

    out = finalize_run(tmp_path)
    assert out is not None
    table = pq.read_table(out)
    assert table.num_rows == 4
    cols = set(table.column_names)
    assert {"module", "qualname", "mean", "shape", "ts_ns", "fingerprint"} <= cols
    assert table.column("module").to_pylist() == ["numpy"] * 4
    assert table.column("shape").to_pylist()[0] == [3]


def test_parquet_finalize_missing_events(tmp_path):
    assert finalize_run(tmp_path) is None


def test_perfetto_errors_without_runs(tmp_path):
    with pytest.raises(PytracerError, match="runs"):
        export_perfetto(tmp_path)


def test_perfetto_errors_without_timestamps(tmp_path):
    run_dir = tmp_path / "runs" / "run-000"
    writer = TraceWriter(run_dir)
    writer.write_event(make_event(ts_ns=None))
    writer.close()
    with pytest.raises(PytracerError, match="timestamped"):
        export_perfetto(tmp_path)


def test_perfetto_span_structure(tmp_path):
    run_dir = tmp_path / "runs" / "run-000"
    writer = TraceWriter(run_dir)
    writer.write_event(make_event(event_id=0, call_id=0, phase="input", ts_ns=1_000))
    writer.write_event(make_event(event_id=1, call_id=0, phase="output", ts_ns=51_000))
    writer.close()
    out = export_perfetto(tmp_path, tmp_path / "t.json")
    payload = json.loads(out.read_text())
    (span,) = [e for e in payload["traceEvents"] if e["ph"] == "X"]
    assert span["name"] == "numpy.sum"
    assert span["dur"] == 50.0  # microseconds
    assert "input:a" in span["args"]
