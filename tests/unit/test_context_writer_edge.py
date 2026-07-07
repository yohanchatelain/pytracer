"""Direct tests: call context, concurrent writer, decorator, summary edges."""

import threading

import numpy as np
from test_events_io import make_event

from pytracer.instrumentation.call_context import CallContext
from pytracer.instrumentation.recorder import Recorder, set_active_recorder
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.summary import summarize_value
from pytracer.trace.writer import TraceWriter


def test_context_parent_stack_nesting():
    ctx = CallContext()
    assert ctx.current_parent() is None
    with ctx.pushed(1):
        assert ctx.current_parent() == 1
        with ctx.pushed(2):
            assert ctx.current_parent() == 2
        assert ctx.current_parent() == 1
    assert ctx.current_parent() is None


def test_context_guard_nesting():
    ctx = CallContext()
    assert not ctx.inside()
    with ctx.guard():
        assert ctx.inside()
        with ctx.guard():
            assert ctx.inside()
        assert ctx.inside()
    assert not ctx.inside()


def test_context_occurrences_independent_per_key():
    ctx = CallContext()
    assert ctx.next_occurrence(("a",)) == 0
    assert ctx.next_occurrence(("a",)) == 1
    assert ctx.next_occurrence(("b",)) == 0


def test_context_caller_source_points_here():
    ctx = CallContext()
    source = ctx.caller_source()
    assert source is not None and source.file.endswith("test_context_writer_edge.py")


def test_context_ids_unique_across_threads():
    ctx = CallContext()
    ids: list[int] = []
    lock = threading.Lock()

    def worker():
        got = [ctx.next_call_id() for _ in range(500)]
        with lock:
            ids.extend(got)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == len(set(ids)) == 4000


def test_writer_concurrent_threads(tmp_path):
    writer = TraceWriter(tmp_path)

    def worker(base):
        for i in range(200):
            writer.write_event(make_event(event_id=base + i, call_id=base + i))

    threads = [threading.Thread(target=worker, args=(k * 200,)) for k in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    writer.close()
    events, truncated = iter_events(writer.path)
    assert not truncated
    assert len(events) == 1600
    assert len({e.event_id for e in events}) == 1600


def test_writer_after_close_is_noop(tmp_path):
    writer = TraceWriter(tmp_path)
    writer.close()
    writer.write_event(make_event())  # must not raise
    writer.close()  # idempotent


def test_decorator_passthrough_without_recorder():
    import pytracer

    @pytracer.trace_function
    def f(x):
        return x * 2

    assert f(21) == 42


def test_decorator_records_with_recorder(tmp_path):
    import pytracer

    @pytracer.trace_function
    def g(x):
        return float(np.sum(x))

    writer = TraceWriter(tmp_path)
    set_active_recorder(Recorder(writer, "run-000"))
    try:
        assert g(np.arange(3.0)) == 3.0
    finally:
        set_active_recorder(None)
        writer.close()
    events, _ = iter_events(writer.path)
    calls = assemble_calls(events)
    assert calls[0].qualname.endswith("g")
    assert calls[0].outputs["Ret"].mean == 3.0


# --- summary edge cases post dtype-aware optimization --------------------------


def test_summary_int_array_skips_float_checks():
    s = summarize_value(np.array([1, 2, 3], dtype=np.int64))
    assert s.nan_count == 0 and s.inf_count == 0 and s.subnormal_count == 0
    assert s.mean == 2.0 and s.linf_norm == 3.0


def test_summary_float32():
    s = summarize_value(np.array([1.5, -4.0], dtype=np.float32))
    assert s.dtype == "float32"
    assert s.linf_norm == 4.0  # from extrema, includes the negative side


def test_summary_all_nan():
    s = summarize_value(np.array([np.nan, np.nan]))
    assert s.nan_count == 2 and s.mean is None


def test_summary_fortran_and_strided():
    a = np.asfortranarray(np.arange(12.0).reshape(3, 4))
    s = summarize_value(a)
    assert s.mean == 5.5 and s.fingerprint is not None
    strided = np.arange(20.0)[::2]
    s2 = summarize_value(strided)
    assert s2.size == 10 and s2.max == 18.0


def test_summary_negative_linf():
    s = summarize_value(np.array([-9.0, 1.0]))
    assert s.linf_norm == 9.0
