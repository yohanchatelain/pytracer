import msgspec
import pytest

from pytracer._errors import PytracerError
from pytracer.trace.event import SCHEMA_VERSION, NumericSummary, SourceRef, TraceEvent
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.writer import TraceWriter


def make_event(event_id=0, call_id=0, phase="input", **kwargs):
    defaults = dict(
        schema_version=SCHEMA_VERSION,
        run_id="run-000",
        event_id=event_id,
        call_id=call_id,
        occurrence=0,
        phase=phase,
        module="numpy",
        qualname="sum",
        arg_name="a" if phase == "input" else "Ret",
        summary=NumericSummary(dtype="float64", shape=(3,), size=3, mean=2.0),
        source=SourceRef(file="/tmp/x.py", lineno=7),
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def test_write_read_roundtrip(tmp_path):
    writer = TraceWriter(tmp_path)
    events = [make_event(event_id=i, call_id=i // 2, phase="input" if i % 2 == 0 else "output")
              for i in range(10)]
    for ev in events:
        writer.write_event(ev)
    writer.close()

    read, truncated = iter_events(writer.path)
    assert not truncated
    assert len(read) == 10
    assert read[0].schema_version == SCHEMA_VERSION
    assert read[0].summary.mean == 2.0
    assert read[0].source == SourceRef(file="/tmp/x.py", lineno=7)


def test_truncated_final_line_tolerated(tmp_path):
    writer = TraceWriter(tmp_path)
    for i in range(3):
        writer.write_event(make_event(event_id=i))
    writer.close()
    raw = writer.path.read_bytes()
    writer.path.write_bytes(raw[:-15])  # cut into the last record

    events, truncated = iter_events(writer.path)
    assert truncated
    assert len(events) == 2


def test_corruption_mid_file_raises(tmp_path):
    writer = TraceWriter(tmp_path)
    for i in range(5):
        writer.write_event(make_event(event_id=i))
    writer.close()
    lines = writer.path.read_bytes().splitlines(keepends=True)
    lines[1] = b'{"garbage": true\n'
    writer.path.write_bytes(b"".join(lines))
    with pytest.raises(PytracerError, match="corrupt"):
        iter_events(writer.path)


def test_assemble_calls_groups_and_orders():
    events = [
        make_event(event_id=0, call_id=0, phase="input"),
        make_event(event_id=1, call_id=0, phase="output"),
        make_event(event_id=2, call_id=1, phase="input", qualname="mean"),
        make_event(event_id=3, call_id=1, phase="exception", note="ValueError: x"),
    ]
    calls = assemble_calls(events)
    assert len(calls) == 2
    assert calls[0].qualname == "sum"
    assert "a" in calls[0].inputs and "Ret" in calls[0].outputs
    assert calls[1].exception == "ValueError: x"


def test_event_json_is_plain_json(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.write_event(make_event())
    writer.close()
    line = writer.path.read_bytes().splitlines()[0]
    decoded = msgspec.json.decode(line)
    assert decoded["module"] == "numpy"
    assert decoded["schema_version"] == SCHEMA_VERSION
