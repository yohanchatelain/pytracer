"""Reproduction tests for Subsystem 1: Core Tracing & Instrumentation bugs.

Covers:
- BUG-CORE-001: Method argument names dropped to Arg0, Arg1 on unbound method invocations
- BUG-CORE-002: T3 TracedArray drops taint tracking on functions returning lists of arrays
- BUG-CORE-003: In-place mutation result is completely lost in TracedUfunc.at
- BUG-CORE-004: In-place flag falsely set on positional out=None in TracedUfunc.__call__
- BUG-CORE-005: Ufunc methods drop in-place flag when out is specified
- BUG-CORE-006: Fortran-contiguous arrays force full array copy during Blake2b fingerprinting
- BUG-CORE-007: T4 Monitor misclassifies callable class instances as C functions
- BUG-CORE-008: T4 Monitor scope filter restricts tracing to script directory
- BUG-CORE-009: Missing single-precision Fortran BLAS GEMM in native shim & census
- BUG-CORE-010: Monitor.stop() writes erroneous available: True when monitor tier is disabled
"""

import json
import tempfile
from pathlib import Path

import numpy as np

from pytracer.instrumentation.monitor import Monitor
from pytracer.instrumentation.native import _GEMM_SYMBOLS, shim_source
from pytracer.instrumentation.patcher import Patcher, ResolvedTarget
from pytracer.instrumentation.recorder import Recorder
from pytracer.instrumentation.tracer_array import TracedArray, rewrap
from pytracer.instrumentation.ufunc import TracedUfunc
from pytracer.trace.reader import iter_events
from pytracer.trace.summary import array_fingerprint
from pytracer.trace.writer import TraceWriter


def test_bug_core_001_unbound_method_argument_names():
    """When a method is called unbound (Class.method(instance, ...)), wrapt binds instance to

    the wrapper and omits it from args. Recorder._bind_arguments fails signature binding
    and falls back to Arg0, Arg1, dropping the real parameter names.
    """

    class Calculator:
        def compute(self, x, y=10):
            return x + y

    with tempfile.TemporaryDirectory() as td:
        w = TraceWriter(td)
        rec = Recorder(w, "run1")
        p = Patcher(rec)
        t = ResolvedTarget(
            "Calculator.compute",
            "calc_mod",
            "Calculator.compute",
            Calculator,
            "compute",
            Calculator.compute,
            "method",
            True,
        )
        p.patch([t])
        calc = Calculator()
        # Unbound method invocation: Calculator.compute(calc, 42, y=20)
        Calculator.compute(calc, 42, y=20)
        w.close()

        events, _ = iter_events(Path(td) / "events.jsonl")
        input_arg_names = [e.arg_name for e in events if e.phase == "input"]
        # Expected: parameter 'x' is retained in recorded argument names
        # Actual on buggy code: ['Arg0', 'y'] ('x' is replaced by 'Arg0')
        assert "x" in input_arg_names, (
            f"Expected parameter name 'x' to be recorded, but got: {input_arg_names}"
        )


def test_bug_core_002_traced_array_list_taint_loss():
    """rewrap() handles ndarray and tuple but omits list, leaving list elements as raw np.ndarray.

    Functions returning a list of arrays have their taint tracking silently dropped.
    """
    arr1 = np.array([1.0, 2.0])
    arr2 = np.array([3.0, 4.0])

    res_list = rewrap([arr1, arr2])
    # Expected: list elements should be wrapped as TracedArray to maintain taint
    # Actual on buggy code: elements remain raw np.ndarray
    assert isinstance(res_list[0], TracedArray), (
        f"Expected TracedArray in list, got {type(res_list[0])}"
    )


def test_bug_core_003_ufunc_at_mutation_lost():
    """TracedUfunc.at delegates with inplace=True, but because np.ufunc.at returns None,

    Recorder._output_items(result) only emits an output event with value=None.
    The in-place mutated array state is completely lost from the trace.
    """
    with tempfile.TemporaryDirectory() as td:
        w = TraceWriter(td)
        rec = Recorder(w, "run1")
        traced_add = TracedUfunc(np.add, rec, "numpy", "add")

        a = np.array([1.0, 2.0, 3.0])
        traced_add.at(a, [0, 1], 10.0)
        w.close()

        events, _ = iter_events(Path(td) / "events.jsonl")
        outputs = [e for e in events if e.phase == "output"]
        # Expected: output event captures mutated array 'a' post-mutation (mean = 8.333...)
        # Actual on buggy code: outputs only contains Ret with summary=None
        has_mutated_output = any(
            e.summary is not None and e.summary.mean is not None for e in outputs
        )
        assert has_mutated_output, (
            f"Expected output event recording in-place mutated array, but got: {outputs}"
        )


def test_bug_core_004_ufunc_call_positional_out_none_inplace():
    """TracedUfunc.__call__ calculates:

    inplace = (kwargs.get("out") is not None) or (len(args) > getattr(self.__wrapped__, "nin", 1))
    When called as ufunc(a, b, None), len(args) > nin is True, erroneously setting inplace=True.
    """
    recorded_inplace: list[bool] = []

    class MockRecorder:
        def record_call(self, *args, **kwargs):
            recorded_inplace.append(kwargs.get("inplace", False))
            return np.add(*kwargs.get("args")[:2])

    rec = MockRecorder()
    traced_add = TracedUfunc(np.add, rec, "numpy", "add")
    a = np.array([1.0, 2.0])
    b = np.array([3.0, 4.0])

    traced_add(a, b, None)
    # Expected: inplace=False because out is None
    # Actual on buggy code: inplace=True because len(args) == 3 > nin == 2
    assert recorded_inplace[0] is False, (
        f"Expected inplace=False when out=None, got {recorded_inplace[0]}"
    )


def test_bug_core_005_ufunc_methods_drop_inplace_flag():
    """TracedUfunc reduce, reduceat, accumulate, and outer call _self_record() without

    passing inplace, defaulting inplace to False even when an out array is provided.
    """
    recorded_inplace: list[bool] = []

    class MockRecorder:
        def record_call(self, *args, **kwargs):
            recorded_inplace.append(kwargs.get("inplace", False))
            return 0

    rec = MockRecorder()
    traced_add = TracedUfunc(np.add, rec, "numpy", "add")
    a = np.array([1.0, 2.0, 3.0])
    out = np.zeros(1)

    traced_add.reduce(a, out=out)
    # Expected: inplace=True when out array is supplied to reduce()
    # Actual on buggy code: inplace=False because inplace parameter is not forwarded
    assert recorded_inplace[0] is True, (
        f"Expected inplace=True for reduce with out=out, got {recorded_inplace[0]}"
    )


def test_bug_core_006_fortran_array_copy_fingerprint():
    """In array_fingerprint(), large arrays take flat = array.reshape(-1) with comment

    '# view: array is contiguous'. For Fortran arrays, reshape(-1) defaults to C-order,
    forcing a full array copy in memory.
    """
    # Large Fortran-contiguous array
    a = np.zeros((2000, 2000), order="F")
    assert a.flags.f_contiguous and not a.flags.c_contiguous

    fp = array_fingerprint(a)
    assert fp is not None
    assert len(fp) == 32
    flat = a.reshape(-1, order="F")
    assert np.shares_memory(a, flat), (
        "array.reshape(-1, order='F') on Fortran array created a full memory copy instead of a view"
    )


def test_bug_core_007_monitor_callable_instance_as_c_call():
    """In Monitor.on_call(), hasattr(callable_obj, '__code__') checks Python functions.

    Callable class instances (defining __call__) do not have __code__ directly on the instance,
    so they are misclassified as C calls and added to c_calls.
    """

    class CustomPythonCallable:
        def __call__(self, x):
            return x * 2

    obj = CustomPythonCallable()
    assert not hasattr(obj, "__code__"), "Instance should not have __code__ attribute directly"

    m = Monitor(scope_dir="/tmp", run_dir="/tmp")
    m._record_call(obj)

    # Expected: Python callable instances should not be recorded as C calls
    # Actual on buggy code: Recorded in m.c_calls
    assert len(m.c_calls) == 0, f"Custom callable was erroneously counted as C call: {m.c_calls}"


def test_bug_core_008_monitor_scope_filter_excludes_project_packages():
    """_bootstrap.py:65 initializes Monitor(scope_dir=Path(script).resolve().parent).

    Monitor._in_scope() only checks filename.startswith(self.scope_dir).
    When running a benchmark or test in a subdirectory, project packages in sibling
    directories (e.g. /workspace/src/my_package) are excluded as out-of-scope.
    """
    # Script in /workspace/benchmarks/run.py
    m = Monitor(scope_dir="/workspace/benchmarks", run_dir="/tmp")

    # Project source code in /workspace/src/pkg/algorithm.py
    is_in_scope = m._in_scope("/workspace/src/pkg/algorithm.py")
    # Expected: project source files outside the script directory are in scope
    # Actual on buggy code: returns False
    assert is_in_scope is True, (
        "Monitor._in_scope rejected project package file outside script parent directory"
    )


def test_bug_core_009_missing_sgemm_symbols_in_native_shim():
    """In pytracer.instrumentation.native, _GEMM_SYMBOLS and blas_shim.c provide interposers for

    double-precision Fortran GEMM, but completely omit single-precision Fortran GEMM.
    """
    c_source = shim_source().read_text()

    # Expected: sgemm_ and scipy_sgemm_64_ are tracked in _GEMM_SYMBOLS and in blas_shim.c
    # Actual on buggy code: both are absent from _GEMM_SYMBOLS and have no C implementation
    assert "sgemm_" in _GEMM_SYMBOLS, "sgemm_ is missing from _GEMM_SYMBOLS"
    assert "scipy_sgemm_64_" in _GEMM_SYMBOLS, "scipy_sgemm_64_ is missing from _GEMM_SYMBOLS"
    assert "void sgemm_(" in c_source, "sgemm_ interposer missing in blas_shim.c"
    assert "void scipy_sgemm_64_(" in c_source, "scipy_sgemm_64_ interposer missing in blas_shim.c"


def test_bug_core_010_monitor_stop_erroneous_available_when_disabled():
    """When the monitor tier is disabled by configuration (e.g. instrumentation='patch'),

    Monitor.start() is not called. However, Monitor.stop() still writes monitor.json
    with 'available': True, falsely implying the monitor ran and found 0 calls.
    """
    with tempfile.TemporaryDirectory() as td:
        m = Monitor(scope_dir="/tmp", run_dir=td)
        # Monitor is never started because it was disabled by configuration
        m.stop()

        monitor_path = Path(td) / "monitor.json"
        assert monitor_path.is_file()
        payload = json.loads(monitor_path.read_text())

        # Expected: when monitor was disabled, monitor.json should reflect available=False
        # Actual on buggy code: payload has {"available": True, "line_counts": {}, "c_calls": {}}
        assert payload.get("available") is False, (
            f"Disabled monitor wrote available: True: {payload}"
        )
