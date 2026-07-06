import numpy as np
import pytest

from pytracer.instrumentation.patcher import Patcher, resolve_targets
from pytracer.instrumentation.recorder import Recorder
from pytracer.trace.reader import assemble_calls, iter_events
from pytracer.trace.writer import TraceWriter


@pytest.fixture
def recorder(tmp_path):
    writer = TraceWriter(tmp_path)
    rec = Recorder(writer, "run-000")
    yield rec
    writer.close()


def read_calls(recorder):
    recorder.writer.close()
    events, _ = iter_events(recorder.writer.path)
    return assemble_calls(events)


def test_resolve_simple_target():
    report = resolve_targets(["numpy.linalg.solve"])
    assert not report.errors
    (t,) = report.resolved
    assert t.module == "numpy.linalg" and t.qualname == "solve" and t.kind == "function"


def test_resolve_ufunc_kind():
    report = resolve_targets(["numpy.add"])
    (t,) = report.resolved
    assert t.kind == "ufunc"


def test_resolve_glob():
    report = resolve_targets(["numpy.linalg.sv*"])
    names = {t.qualname for t in report.resolved}
    assert "svd" in names
    assert not report.errors


def test_resolve_errors_reported_not_raised():
    report = resolve_targets(["numpy.linalg.nonexistent", "no_such_module_xyz.f"])
    assert len(report.errors) == 2
    assert not report.resolved


def test_patch_preserves_result_and_records(recorder):
    report = resolve_targets(["numpy.sum"])
    original = np.sum
    with Patcher(recorder) as patcher:
        patcher.patch(report.resolved)
        assert np.sum is not original
        result = np.sum(np.array([1.0, 2.0, 3.0]))
    assert np.sum is original  # exact restoration
    assert result == 6.0

    calls = read_calls(recorder)
    assert len(calls) == 1
    call = calls[0]
    assert call.module == "numpy" and call.qualname == "sum"
    assert call.outputs["Ret"].mean == 6.0
    assert call.inputs  # bound argument summaries present


def test_patch_idempotent(recorder):
    report = resolve_targets(["numpy.sum"])
    patcher = Patcher(recorder)
    patcher.patch(report.resolved)
    patcher.patch(report.resolved)  # second patch is a no-op
    np.sum(np.arange(3.0))
    patcher.unpatch()
    assert not isinstance(np.sum, object().__class__.__mro__[0]) or callable(np.sum)
    calls = read_calls(recorder)
    assert len(calls) == 1  # not double-recorded


def test_patched_signature_preserved(recorder):
    import inspect

    report = resolve_targets(["numpy.linalg.solve"])
    with Patcher(recorder) as patcher:
        patcher.patch(report.resolved)
        sig = inspect.signature(np.linalg.solve)
        assert "a" in sig.parameters and "b" in sig.parameters


def test_exception_recorded_and_reraised(recorder):
    report = resolve_targets(["numpy.linalg.solve"])
    with Patcher(recorder) as patcher:
        patcher.patch(report.resolved)
        with pytest.raises(np.linalg.LinAlgError):
            np.linalg.solve(np.zeros((2, 2)), np.ones(2))
    calls = read_calls(recorder)
    assert calls[0].exception and "Singular" in calls[0].exception


def test_inherited_method_unpatch_deletes(recorder):
    class Base:
        def compute(self, x):
            return x + 1

    class Child(Base):
        pass

    import sys

    module = sys.modules[__name__]
    module.Base = Base
    module.Child = Child
    try:
        report = resolve_targets([f"{__name__}.Child.compute"])
        assert not report.errors
        (t,) = report.resolved
        assert not t.owned  # inherited from Base
        patcher = Patcher(recorder)
        patcher.patch(report.resolved)
        assert "compute" in vars(Child)
        assert Child().compute(1) == 2
        patcher.unpatch()
        assert "compute" not in vars(Child)  # inheritance restored, not copied
        assert Child().compute(1) == 2
    finally:
        del module.Base, module.Child


def test_reentrancy_guard_no_recursion(recorder):
    # summarize_value uses numpy internally; tracing numpy.mean while
    # summarizing a numpy.mean call must not recurse.
    report = resolve_targets(["numpy.mean", "numpy.std", "numpy.count_nonzero"])
    with Patcher(recorder) as patcher:
        patcher.patch(report.resolved)
        result = np.mean(np.array([1.0, 2.0, 3.0]))
    assert result == 2.0
    calls = read_calls(recorder)
    assert len(calls) == 1  # only the user-level call, no internal echoes


def test_occurrence_deterministic(recorder):
    report = resolve_targets(["numpy.sum"])
    with Patcher(recorder) as patcher:
        patcher.patch(report.resolved)
        for _ in range(3):
            np.sum(np.arange(4.0))
    calls = read_calls(recorder)
    assert [c.occurrence for c in calls] == [0, 1, 2]


def test_parent_linkage_for_nested_calls(recorder):
    report = resolve_targets(["numpy.sum", f"{__name__}.outer_fn"])
    import sys

    def outer_fn(x):
        return np.sum(x) * 2

    sys.modules[__name__].outer_fn = outer_fn
    try:
        report = resolve_targets([f"{__name__}.outer_fn", "numpy.sum"])
        with Patcher(recorder) as patcher:
            patcher.patch(report.resolved)
            sys.modules[__name__].outer_fn(np.arange(3.0))
        calls = read_calls(recorder)
        by_name = {c.qualname: c for c in calls}
        assert by_name["sum"].parent_call_id == by_name["outer_fn"].call_id
    finally:
        del sys.modules[__name__].outer_fn
