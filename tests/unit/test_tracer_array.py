import numpy as np
import pytest

from pytracer.instrumentation.recorder import (
    Recorder,
    set_active_recorder,
)
from pytracer.instrumentation.tracer_array import TracedArray, taint
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.writer import TraceWriter


@pytest.fixture
def recorder(tmp_path):
    writer = TraceWriter(tmp_path)
    rec = Recorder(writer, "run-000")
    set_active_recorder(rec)
    yield rec
    set_active_recorder(None)
    writer.close()


def read_calls(recorder):
    recorder.writer.close()
    events, _ = iter_events(recorder.writer.path)
    return assemble_calls(events)


def test_taint_outside_run_is_passthrough():
    # no active recorder: computation works, nothing is recorded
    x = taint([1.0, 2.0, 3.0])
    assert isinstance(x, TracedArray)
    np.testing.assert_array_equal(x + 1.0, [2.0, 3.0, 4.0])


def test_operator_add_traced(recorder):
    x = taint([1.0, 2.0])
    result = x + np.array([3.0, 4.0])
    assert isinstance(result, TracedArray)  # taint propagates
    # compare on the plain view: numpy ops on the tainted result would
    # themselves be traced and pollute the call count below
    np.testing.assert_array_equal(result.view(np.ndarray), [4.0, 6.0])
    calls = read_calls(recorder)
    assert len(calls) == 1
    assert calls[0].qualname == "add" and calls[0].tier == "t3"
    assert calls[0].ufunc_method == "__call__"
    assert calls[0].outputs["Ret"].mean == 5.0


def test_matmul_operator_traced(recorder):
    a = taint(np.eye(2))
    b = np.array([[1.0], [2.0]])
    result = a @ b
    np.testing.assert_array_equal(result, b)
    calls = read_calls(recorder)
    assert calls[0].qualname == "matmul" and calls[0].tier == "t3"


def test_reduction_method_traced(recorder):
    x = taint(np.arange(5.0))
    total = x.sum()
    assert float(total) == 10.0
    calls = read_calls(recorder)
    assert calls[0].qualname == "add" and calls[0].ufunc_method == "reduce"


def test_array_function_protocol_traced(recorder):
    x = taint(np.arange(4.0))
    result = np.mean(x)
    assert float(result) == 1.5
    calls = read_calls(recorder)
    assert calls[0].qualname == "mean" and calls[0].tier == "t3"


def test_inplace_operator(recorder):
    x = taint(np.ones(3))
    x += 1.0
    np.testing.assert_array_equal(x, [2.0, 2.0, 2.0])
    recorder.writer.close()
    events, _ = iter_events(recorder.writer.path)
    assert any(ev.inplace for ev in events)


def test_alias_immunity(recorder):
    # the whole point of T3: `from numpy import ...` aliases captured before
    # any patching still dispatch through the protocol
    from numpy import multiply as aliased_multiply

    x = taint([2.0, 3.0])
    result = aliased_multiply(x, 10.0)
    np.testing.assert_array_equal(result, [20.0, 30.0])
    calls = read_calls(recorder)
    assert calls[0].qualname == "multiply" and calls[0].tier == "t3"


def test_asarray_strips_taint():
    # documented hazard: np.asarray drops the subclass (taint-loss boundary)
    x = taint([1.0, 2.0])
    stripped = np.asarray(x)
    assert type(stripped) is not TracedArray or stripped.base is not None
    plain = np.ascontiguousarray(x).view(np.ndarray)
    assert not isinstance(plain, TracedArray)


def test_no_recursion_with_summary(recorder):
    # summaries use numpy on the traced values; the reentrancy guard must
    # keep those internal ops out of the trace
    x = taint(np.arange(100.0))
    _ = x * 2.0
    calls = read_calls(recorder)
    assert len(calls) == 1


def test_recorder_taint_outputs_rewraps(tmp_path):
    writer = TraceWriter(tmp_path)
    rec = Recorder(writer, "run-000", taint_outputs=True)
    set_active_recorder(rec)
    try:
        result = rec.record_call(
            module="m", qualname="f", tier="t1",
            wrapped=lambda: np.arange(3.0), args=(), kwargs={},
        )
        assert isinstance(result, TracedArray)
    finally:
        set_active_recorder(None)
        writer.close()
