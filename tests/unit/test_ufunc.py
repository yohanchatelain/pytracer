import numpy as np
import pytest

from pytracer.instrumentation.patcher import Patcher, resolve_targets
from pytracer.instrumentation.recorder import Recorder
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.writer import TraceWriter


@pytest.fixture
def patched_add(tmp_path):
    writer = TraceWriter(tmp_path)
    recorder = Recorder(writer, "run-000")
    report = resolve_targets(["numpy.add"])
    patcher = Patcher(recorder)
    patcher.patch(report.resolved)
    yield recorder
    patcher.unpatch()
    writer.close()


def read_calls(recorder):
    recorder.writer.close()
    events, _ = iter_events(recorder.writer.path)
    return assemble_calls(events)


def test_isinstance_preserved(patched_add):
    assert isinstance(np.add, np.ufunc)
    assert np.add.nin == 2 and np.add.nout == 1


def test_call_result_and_event(patched_add):
    result = np.add(np.array([1.0, 2.0]), np.array([3.0, 4.0]))
    np.testing.assert_array_equal(result, [4.0, 6.0])
    calls = read_calls(patched_add)
    assert len(calls) == 1
    assert calls[0].ufunc_method == "__call__"
    assert calls[0].outputs["Ret"].mean == 5.0


def test_reduce_method_tagged(patched_add):
    total = np.add.reduce(np.arange(5.0))
    assert total == 10.0
    calls = read_calls(patched_add)
    assert calls[0].ufunc_method == "reduce"
    assert calls[0].function == "numpy.add.reduce"


def test_accumulate_and_outer(patched_add):
    np.testing.assert_array_equal(np.add.accumulate(np.arange(3.0)), [0.0, 1.0, 3.0])
    assert np.add.outer(np.arange(2), np.arange(2)).shape == (2, 2)
    methods = [c.ufunc_method for c in read_calls(patched_add)]
    assert methods == ["accumulate", "outer"]


def test_at_inplace(patched_add):
    a = np.array([1.0, 2.0, 3.0])
    np.add.at(a, [0, 1], 10.0)
    np.testing.assert_array_equal(a, [11.0, 12.0, 3.0])
    calls = read_calls(patched_add)
    assert calls[0].ufunc_method == "at"


def test_out_argument_flagged(patched_add):
    out = np.empty(2)
    np.add(np.ones(2), np.ones(2), out=out)
    np.testing.assert_array_equal(out, [2.0, 2.0])
    patched_add.writer.close()
    events, _ = iter_events(patched_add.writer.path)
    assert any(ev.inplace for ev in events)


def test_unpatch_restores_real_ufunc(tmp_path):
    writer = TraceWriter(tmp_path)
    recorder = Recorder(writer, "run-000")
    original = np.add
    report = resolve_targets(["numpy.add"])
    patcher = Patcher(recorder)
    patcher.patch(report.resolved)
    assert np.add is not original
    patcher.unpatch()
    assert np.add is original
    writer.close()


def test_operator_dispatch_documented_blind_spot(patched_add):
    # a + b goes through ndarray C slots, not the module attribute: no event.
    # This test pins the declared T2 contract (plan §1.2).
    a = np.ones(3)
    b = np.ones(3)
    _ = a + b
    assert read_calls(patched_add) == []
