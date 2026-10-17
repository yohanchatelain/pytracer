# pytracer Code Review, Architecture Audit & Complete Bug Catalog

**Document Version**: 2.0.0-AUDIT  
**Date**: 2026-10-17  
**Target Repository**: `pytracer` (v2.0.0 Clean-Slate Architecture)  
**Author / Auditor**: Pytracer Bug Catalog Worker  
**Repository State**: Read-Only Core Library Preservation (`git status --porcelain pytracer/` is empty)  

---

## 1. Executive Summary & Codebase Architecture Review

### 1.1 Executive Summary
`pytracer` is an automated numerical variability profiler and perturbation analysis engine for scientific Python programs. Originally conceived as a dynamic floating-point instability detector, version 2.0.0 represents a clean-slate architecture targeting Python 3.12+, utilizing process isolation, a 5-tier instrumentation stack, append-safe JSONL event logging, Parquet analytical export, and interactive Dash/Perfetto visualization.

An exhaustive codebase audit was conducted across all 5 primary architectural subsystems of `pytracer`. The audit confirmed **30 distinct defects** (2 Critical, 10 High, 14 Medium, 4 Low):
- **Subsystem 1 (Core Tracing & Instrumentation)**: 10 defects (BUG-CORE-001 through BUG-CORE-010)
- **Subsystem 2 (Data Storage & Serialization)**: 6 defects (BUG-STORE-001 through BUG-STORE-006)
- **Subsystem 3 (Numerical/Statistical Analysis & Visualization)**: 7 defects (BUG-NUM-001 through BUG-NUM-005, BUG-VIS-001 through BUG-VIS-002)
- **Subsystem 4 (Python 3 & Modern Dependency Compatibility)**: 3 defects (BUG-COMPAT-001 through BUG-COMPAT-003)
- **Subsystem 5 (CLI Entrypoints & Configuration)**: 4 defects (BUG-CLI-001 through BUG-CLI-004)

Crucially, throughout this entire audit and verification process, the **Core Library Preservation** constraint has been strictly maintained: `git status --porcelain pytracer/` is verified completely empty, and no files within `pytracer/` or `src/pytracer/` have been modified or deleted.

---

### 1.2 Architectural Review Across the 5 Subsystems

```
                                      +------------------------------------+
                                      |           pytracer CLI             |
                                      |     (cli/main.py, doctor.py)       |
                                      +-----------------+------------------+
                                                        |
                                                        v
                                      +------------------------------------+
                                      |       Experiment Runner            |
                                      |   (experiment.py, _bootstrap.py)   |
                                      +-----------------+------------------+
                                                        |
       +------------------------------------------------+------------------------------------------------+
       |                                                |                                                |
       v                                                v                                                v
+-----------------------------+          +-----------------------------+          +-----------------------------+
|        Subsystem 1:         |          |        Subsystem 2:         |          |        Subsystem 3:         |
|   Core Instrumentation      |          |    Storage & Persistence    |          |    Analysis & Visualizer    |
| - T1 Patcher (wrapt)        |          | - msgspec JSONL stream      |          | - Callsite & LCS Alignment  |
| - T2 TracedUfunc            | -------> | - Array payloads (npy/zarr) | -------> | - Precision (sig_bits)      |
| - T3 TracedArray (taint)    |          | - Parquet export (zstd)     |          | - Quality Gates (check.py)  |
| - T4 sys.monitoring         |          | - Trace Reassembly (reader) |          | - Dash Interactive GUI      |
| - T5 Native BLAS shim (C)   |          | - Perfetto Chrome Trace     |          | - Markdown / HTML Reports   |
+-----------------------------+          +-----------------------------+          +-----------------------------+
       ^                                                                                         ^
       |                                                                                         |
       +-----------------------------------+-----------------------------------------------------+
                                           |
                                           v
                       +---------------------------------------+
                       |        Subsystems 4 & 5:              |
                       | Modern Compatibility & CLI Pipelines  |
                       | - Python 3.12+ stdlib compatibility   |
                       | - NumPy 2.x & SciPy BLAS integration  |
                       | - Dash 4+ / Plotly 6 modernization    |
                       +---------------------------------------+
```

#### Subsystem 1: Core Tracing & Instrumentation Correctness
The core instrumentation framework (`pytracer.instrumentation`) provides a 5-tier hierarchical capture model:
1. **Tier 1 (T1 Patcher - Function & Method Interposition)**: Uses `wrapt.FunctionWrapper` to dynamically wrap targeted callables (`pytracer.instrumentation.patcher`). Resolves explicit target strings, wildcards (`numpy.linalg.*`), and module prefixes.
2. **Tier 2 (T2 TracedUfunc - NumPy Universal Functions)**: Wraps universal functions (`np.ufunc`) to intercept both direct calls (`__call__`) and methods (`reduce`, `accumulate`, `reduceat`, `outer`, `at`).
3. **Tier 3 (T3 TracedArray - Taint Propagation)**: Subclasses `np.ndarray` and implements `__array_ufunc__` and `__array_function__` protocols to trace downstream operations executed on perturbed array outputs without requiring explicit function patching.
4. **Tier 4 (T4 Monitor - PEP 669 sys.monitoring)**: Uses Python 3.12's `sys.monitoring` tool ID `PROFILER_ID` to capture line execution frequencies and uninstrumented C extension invocations.
5. **Tier 5 (T5 Native Census - C LD_PRELOAD Shim)**: Uses an interposed shared library (`blas_shim.c`) compiled on Linux to log dynamically linked BLAS/LAPACK entrypoints (`cblas_dgemm`, `dgemm_`, `scipy_cblas_dgemm64_`, `dgesv_`).

*Architectural Findings*: While the multi-tiered model is elegant, several critical edge cases break invariants:
- Signature binding fails on unbound method invocations because `instance` is not forwarded to `record_call`, stripping parameter names to `Arg0`, `Arg1` (BUG-CORE-001).
- T3 array taint tracking breaks when functions return lists of arrays (like `np.split`), because `rewrap()` handles tuples but omits lists (BUG-CORE-002).
- In-place mutation results (`np.ufunc.at`) are completely lost because `recorder.py` emits the return value (`None`) rather than the mutated input array (BUG-CORE-003).
- The T4 monitor classifies user-defined callable class instances as native C functions due to checking `hasattr(callable_obj, "__code__")` directly on the instance (BUG-CORE-007).
- Scoping in the T4 monitor resolves strictly to `Path(script).parent`, ignoring project packages and parent directory libraries (BUG-CORE-008).
- The native BLAS shim completely omits single-precision Fortran entry points (`sgemm_`, `scipy_sgemm_64_`) (BUG-CORE-009).

#### Subsystem 2: Data Storage, Serialization & Trace Loading/Replay
The storage subsystem (`pytracer.storage`, `pytracer.trace`) handles high-throughput serialization of runtime traces:
1. **Wire Format Event Model (`event.py`)**: Defined via `msgspec.Struct` records (`TraceEvent`, `NumericSummary`, `SourceRef`) adhering to `SCHEMA_VERSION = "2.0.0"`.
2. **Streaming Capture (`writer.py`)**: `TraceWriter` writes newline-delimited JSON (`events.jsonl`) using thread-safe locking and flushes every 200 events (`FLUSH_EVERY = 200`).
3. **Trace Reassembly (`reader.py`)**: `iter_events()` decodes lines from raw bytes with crash-truncation tolerance; `assemble_calls()` reconstructs hierarchically linked `CallRecord` entries keyed by `CallKey`.
4. **Payload Storage (`arrays.py`)**: Arrays are persisted to disk using `.npy` (NumPy binary) or `.zarr` (Zarr hierarchy).
5. **Analytical Archiving (`parquet.py`)**: `finalize_run()` compiles `events.jsonl` into an `events.parquet` table with Zstandard compression.
6. **Execution Span Export (`perfetto.py`)**: Exports event spans to Chrome Trace/Perfetto format (`trace.perfetto.json`).

*Architectural Findings*:
- The Parquet table omits the `payload_ref` column, severing the link between tabular events and stored array binaries in downstream analytical tools (BUG-STORE-001).
- Storage using Zarr 3.x encounters `zarr.errors.ContainsArrayError` on repeated writes, which `ArrayStore.maybe_store` catches and silently swallows, causing payload loss (BUG-STORE-002).
- `iter_events` relies on naive line counting (`i >= last_index - 1`), causing trailing blank lines to convert benign crash truncations into unhandled `PytracerError` crashes (BUG-STORE-003).
- Multiple unnamed output events overwrite each other under the hardcoded key `"Ret"` in `assemble_calls` (BUG-STORE-004).
- Output events with `arg_name=None` are silently omitted from Perfetto spans (BUG-STORE-005).
- Storage dependencies contain phantom packages (`numcodecs`) and format portability issues across Zarr 2 vs 3 (BUG-STORE-006).

#### Subsystem 3: Numerical/Statistical Analysis & Visualization
The numerical analysis pipeline (`pytracer.analysis`, `pytracer.dashboard`, `pytracer.report`) transforms raw execution traces into actionable precision metrics:
1. **Sequence Alignment (`align.py`)**: Supports `callsite` (exact occurrence matching), `strict` (raises on divergence), and `fuzzy` (LCS alignment using `difflib.SequenceMatcher` over argument shape/dtype signatures).
2. **Significance & Stability (`aggregate.py`)**: Computes scalar standard deviation across runs (`sig_bits = -log2(std / |mean|)`, capped at 53 bits for IEEE 754 float64). Computes digit amplification (`max_amplification_bits = min(input_sigs) - min(output_sigs)`).
3. **Element-wise Profiling (`elementwise.py`)**: Evaluates cell-by-cell numerical stability on aligned 3D/ND stacked array payloads.
4. **CI Quality Gates (`check.py`)**: Evaluates experiment results against user thresholds (`min_sig_bits`, `max_divergence`, `allow_nan`, `allow_inf`).
5. **Differential Analysis (`diff.py`)**: Computes regression matrices between two experiments (A/B testing).
6. **Interactive Dashboard (`dashboard/`)**: A 5-tab Dash/Plotly application (Overview, Explorer, Call Graph, Execution Gantt, Diff Waterfall).
7. **Reporting (`report/`)**: Formats summaries into Markdown, JSON, and HTML.

*Architectural Findings*:
- `stack_arrays()` only checks `arrays[0]` for complex dtype. In mixed-type runs where Run 1 produces a complex array, NumPy casts the stack to real with `ComplexWarning`, discards the imaginary component, and falsely reports exact 53.0-bit stability (BUG-NUM-001).
- Total non-finite outputs (100% NaN/Inf) bypass `pytracer check` quality gates completely because `nan_instability` requires variance between runs, and `min_output_sig_bits` is `None` (BUG-NUM-002).
- Sporadic NaN runs are silently dropped by `sig_bits()`, allowing an intermittently failing algorithm to be reported as having perfect 53-bit precision (BUG-NUM-003).
- The web dashboard ignores control-flow divergence regressions during A/B diff comparisons (BUG-NUM-004).
- Exact float equality in `diff.py` triggers spurious divergence warnings on machine epsilon differences (BUG-NUM-005).
- Dash DataTable row indexing in `active_cell` references the unsorted table dataset, causing the GUI to open unrelated functions in the Explorer tab (BUG-VIS-001).
- HTML report generation dumps raw Markdown into `<pre>`, rendering all stylesheet styling dead (BUG-VIS-002).

#### Subsystem 4: Python 3 Compatibility & Modern Dependency Compatibility
`pytracer` is designed for modern Python environments:
- Standard library: Uses Python 3.12+ `sys.monitoring`, `datetime.UTC`, and `tomllib`.
- NumPy: Compatible with NumPy 2.x array dispatching protocols (`__array_ufunc__`, `__array_function__`).
- SciPy: Integrates with modern `scipy-openblas` ILP64 64-bit BLAS symbols.
- Dash / Plotly: Uses modern callback triggers (`dash.ctx`).

*Architectural Findings*:
- Instantiation of `dash_table.DataTable` emits `DeprecationWarning` under Dash 4.4.1, failing CI runs configured with strict warning gating (`-W error::Warning`) (BUG-COMPAT-001).
- `scikit-learn` is missing from `pyproject.toml`, resulting in permanent test skip for the built-in sklearn plugin (BUG-COMPAT-002).
- `pytracer doctor` reports Python < 3.12 as a soft warning (`WARN`) with exit code 0 instead of a hard error (`FAIL`), misleading users about supported runtime environments (BUG-COMPAT-003).

#### Subsystem 5: CLI Entrypoints, Runner Execution & Configuration
The command-line interface (`pytracer.cli`) orchestrates all user interactions:
- Subcommands: `init`, `run`, `analyze`, `report`, `check`, `diff`, `dash`, `export`, `doctor`, `config`, `plugins`.
- Execution Orchestration (`pytracer.experiment`): Executes multiple child runs via `pytracer._bootstrap`, injecting perturbation environment variables (`VFC_*`, `VERROU_*`, `LD_PRELOAD`).

*Architectural Findings*:
- `experiment.py` forces `cwd=str(script_path.parent)` when spawning child processes, breaking scripts that reference data files relative to the project root (BUG-CLI-001).
- The CLI completely lacks a `--config` option, preventing users from passing explicit configuration files (BUG-CLI-002).
- `pytracer check` silently ignores functions with missing or `None` output significance, passing them under `--min-sig-bits` (BUG-CLI-003).
- Target resolution in `Patcher.resolve_targets()` fails on class wildcards (e.g. `scipy.optimize.OptimizeResult.*`) because it attempts to import the class name as a module prefix (BUG-CLI-004).

---

## 2. Baseline Test Suite Execution

### 2.1 Test Environment Specification

| Parameter | Specification | Verification Command / Source |
|---|---|---|
| **Operating System** | Linux 5.15.167.4-microsoft-standard-WSL2 (x86_64, Ubuntu 24.04 LTS) | `uname -a` |
| **Python Interpreter** | CPython 3.12.3 (`/home/yohan/Work/pytracer/.venv/bin/python`) | `python --version` |
| **Test Runner** | pytest 9.1.1 | `pytest --version` |
| **Active Pytest Plugins** | `dash-4.4.1`, `zarr-3.3.0`, `cov-7.1.0` | pytest session header |
| **Core Dependencies** | `numpy 2.5.2`, `scipy 1.18.0`, `wrapt 2.3.0`, `msgspec 0.21.1`, `pyarrow 25.0.1` | `pytracer doctor` |
| **Analysis & Storage** | `significantdigits 0.6.0`, `zarr 3.3.0`, `pandas 3.0.5`, `tomli-w 1.2.0` | `pip list` |
| **Visualization & Reporting** | `dash 4.4.1`, `plotly 6.9.0`, `jinja2 3.1.6` | `pip list` |
| **Native Toolchain** | `/usr/bin/cc` (gcc 13.3.0) | `which cc` |

---

### 2.2 Baseline Test Execution Results

The baseline execution was run against the untouched repository:
```bash
./.venv/bin/pytest -v -W default -ra
```

#### Outcome Metrics
- **Total Tests Collected**: 205
- **Passed**: 204
- **Skipped**: 1
- **Failed**: 0
- **Errors**: 0
- **Deprecation Warnings**: 11 occurrences (5 unique test call sites)
- **Execution Duration**: 65.08s (0:01:05)
- **Exit Code**: 0

#### Analysis of Skipped Test
```text
SKIPPED [1] tests/integration/test_sci_plugins.py:45: sklearn not installed
```
- **Test File**: `tests/integration/test_sci_plugins.py`
- **Function**: `test_sklearn_plugin_traces_fit`
- **Skip Condition**: `@pytest.mark.skipif(importlib.util.find_spec("sklearn") is None, reason="sklearn not installed")`
- **Root Cause Analysis**: The built-in plugin `_sklearn_plugin` in `src/pytracer/plugins/registry.py` is fully implemented and tested. However, `scikit-learn` was omitted from `pyproject.toml` under `dependencies` and `optional-dependencies`. When developer or CI environments sync with `uv sync` or `pip install -e ".[all]"`, `scikit-learn` is not installed, leaving this integration test permanently unexecuted.

#### Analysis of Deprecation Warnings
```text
tests/integration/test_dashboard_export.py::test_dashboard_builds
tests/integration/test_dashboard_export.py::test_dashboard_builds
tests/integration/test_dashboard_export.py::test_dashboard_compare_mode
tests/integration/test_dashboard_export.py::test_dashboard_compare_mode
tests/integration/test_dashboard_export.py::test_dashboard_compare_mode
  /home/yohan/Work/pytracer/.venv/lib/python3.12/site-packages/dash/development/base_component.py:159: DeprecationWarning: 
  The dash_table.DataTable will be removed from the builtin dash components in a future major version.
  We recommend using dash-ag-grid as a replacement. Install with `pip install dash[ag-grid]`.
    self._validate_deprecation()
```
- **Category**: `DeprecationWarning`
- **Trigger**: Instantiation of `dash_table.DataTable` across dashboard layouts (`src/pytracer/dashboard/layout.py:56, 499`).
- **Impact**: In modern strict CI pipelines where pytest is invoked with `-W error::Warning`, these warnings immediately cause tests `test_dashboard_builds` and `test_dashboard_compare_mode` to fail with exit code 1.

---

## 3. Complete Defect Catalog (All 30 Confirmed Defects)

### Subsystem 1: Core Tracing & Instrumentation Correctness

#### BUG-CORE-001: Method argument names dropped to Arg0, Arg1 on unbound method invocations
- **Unique ID**: `BUG-CORE-001`
- **Severity**: High
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/recorder.py:126-138`, `src/pytracer/instrumentation/patcher.py:206-216`
- **Root Cause Analysis**:
  In `patcher.py`, `_traced(wrapped, instance, args, kwargs)` is generated by `wrapt.FunctionWrapper`. When a method is called unbound (e.g. `Class.method(instance, *args)`), `wrapt` extracts `instance` into the wrapper parameter, leaving `args` with only the trailing arguments. However, `patcher.py` invokes `recorder.record_call()` without passing `instance`.
  Inside `recorder.py:_bind_arguments()`, `_cached_signature(bind_with).bind(*args, **kwargs)` is called on the unbound method signature. That signature expects `(self, *args)`. Because `args` does not contain `self`, `sig.bind()` raises `TypeError: missing a required argument: ...`.
  The error is silently swallowed by `except (ValueError, TypeError): pass`, falling back to `named = {f"Arg{i}": v for i, v in enumerate(args)}`.
- **Actual Behavior**:
  Unbound class method calls drop parameter names and record all arguments as generic `Arg0`, `Arg1`.
- **Expected Behavior**:
  `_traced` forwards `instance` to `record_call`, and `_bind_arguments` binds `instance` so that declared parameter names (`X`, `y`, etc.) are preserved.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_001_unbound_method_arg_names` / `python reproduce_bugs.py --bug BUG-CORE-001`

---

#### BUG-CORE-002: T3 TracedArray drops taint tracking on functions returning lists of arrays
- **Unique ID**: `BUG-CORE-002`
- **Severity**: High
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/tracer_array.py:37-45`
- **Root Cause Analysis**:
  In `src/pytracer/instrumentation/tracer_array.py`, `_unwrap()` properly handles both `tuple` and `list` structures. However, `rewrap(value)` only checks `isinstance(value, tuple)`. It omits `isinstance(value, list)`.
  When a scientific function (such as `np.split()`, `np.hsplit()`, `np.array_split()`, or custom user routines) returns a `list` of arrays, `rewrap` hits `return value` without converting the elements to `TracedArray` views.
- **Actual Behavior**:
  Arrays returned in lists lose their `TracedArray` wrapper; downstream operations on these arrays are not intercepted by T3 taint tracking.
- **Expected Behavior**:
  `rewrap` recursively wraps arrays contained in both tuples and lists.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_002_traced_array_list_taint_loss` / `python reproduce_bugs.py --bug BUG-CORE-002`

---

#### BUG-CORE-003: In-place mutation result is completely lost in TracedUfunc.at
- **Unique ID**: `BUG-CORE-003`
- **Severity**: High
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/ufunc.py:59-60`, `src/pytracer/instrumentation/recorder.py:218-220`
- **Root Cause Analysis**:
  `np.ufunc.at` (e.g. `np.add.at(a, indices, b)`) performs in-place unbuffered array mutations and returns `None`. `TracedUfunc.at()` calls `self._self_record("at", ..., inplace=True)`.
  In `recorder.py:218-220`, the recorder constructs output events via `self._output_items(result)`. Because `result` is `None`, `self._output_items(None)` yields `[("Ret", None)]`. The mutated array `args[0]` is never recorded as an output event.
- **Actual Behavior**:
  `np.ufunc.at` calls record an output of `Ret: None`; the post-mutation array values and statistics are permanently lost.
- **Expected Behavior**:
  When `inplace=True` or `method=="at"`, `recorder.py` records the mutated target array (`args[0]`) as the output event.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_003_ufunc_at_mutation_lost` / `python reproduce_bugs.py --bug BUG-CORE-003`

---

#### BUG-CORE-004: In-place flag falsely set on positional out=None in TracedUfunc.__call__
- **Unique ID**: `BUG-CORE-004`
- **Severity**: Medium
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/ufunc.py:42-44`
- **Root Cause Analysis**:
  In `TracedUfunc.__call__()`:
  ```python
  inplace = (kwargs.get("out") is not None) or (
      len(args) > getattr(self.__wrapped__, "nin", 1)
  )
  ```
  If a caller passes `out=None` positionally (e.g. `np.sin(x, None)` where `nin=1`, `len(args)=2` or `np.add(x, y, None)` where `nin=2`, `len(args)=3`), `len(args) > nin` evaluates to `True`, falsely setting `inplace=True`.
- **Actual Behavior**:
  Pure ufunc invocations passing positional `out=None` are falsely marked with `inplace=True`.
- **Expected Behavior**:
  `inplace=True` should only be set if the positional output argument at index `nin` is not `None`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_004_ufunc_call_positional_out_none` / `python reproduce_bugs.py --bug BUG-CORE-004`

---

#### BUG-CORE-005: Ufunc methods (reduce, accumulate, outer) silently drop in-place flag when out is specified
- **Unique ID**: `BUG-CORE-005`
- **Severity**: Medium
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/ufunc.py:47-58`
- **Root Cause Analysis**:
  The wrapper methods `reduce()`, `reduceat()`, `accumulate()`, and `outer()` call `self._self_record()` without checking if `out` was supplied in `args` or `kwargs`. `inplace` defaults to `False`.
- **Actual Behavior**:
  In-place ufunc reductions (e.g. `np.add.reduce(a, out=out)`) have `inplace=False` in trace events.
- **Expected Behavior**:
  When `out` is supplied, `inplace=True` is recorded.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_005_ufunc_methods_drop_inplace` / `python reproduce_bugs.py --bug BUG-CORE-005`

---

#### BUG-CORE-006: Fortran-contiguous large arrays force full array copy during Blake2b fingerprinting
- **Unique ID**: `BUG-CORE-006`
- **Severity**: Medium
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/trace/summary.py:96-99`
- **Root Cause Analysis**:
  In `array_fingerprint()`:
  ```python
  elif array.flags.c_contiguous or array.flags.f_contiguous:
      flat = array.reshape(-1)  # view: array is contiguous
  ```
  `array.reshape(-1)` defaults to C-ordering (`order='C'`). When called on an F-contiguous array (`flags.f_contiguous=True, flags.c_contiguous=False`), NumPy cannot construct a C-order flattened view. It allocates a brand-new contiguous memory buffer of `array.nbytes` and copies the entire array into RAM.
- **Actual Behavior**:
  Fingerprinting a large Fortran array allocates a full duplicate copy in memory, violating the bounded-memory contract and risking OOM on large matrices.
- **Expected Behavior**:
  Fingerprinting uses `ravel(order='K')` or `reshape(-1, order='F')` to obtain a non-copying view.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_006_fortran_array_fingerprint_copy` / `python reproduce_bugs.py --bug BUG-CORE-006`

---

#### BUG-CORE-007: T4 Monitor misclassifies callable class instances as C functions
- **Unique ID**: `BUG-CORE-007`
- **Severity**: Medium
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/monitor.py:60-66`
- **Root Cause Analysis**:
  In `on_call()`:
  ```python
  if hasattr(callable_obj, "__code__"):
      return None
  ...
  self.c_calls[f"{mod}.{name}" if mod else name] += 1
  ```
  Python functions have `__code__`, but instances of user classes implementing `__call__` do not have `__code__` on the instance itself (it lives on `type(callable_obj).__call__.__code__`). Because `hasattr(callable_obj, "__code__")` evaluates to `False`, the monitor logs the call in `self.c_calls`.
- **Actual Behavior**:
  Python callable class instances are misclassified as C functions in `monitor.json`.
- **Expected Behavior**:
  Callable class instances are recognized as Python code.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_007_monitor_callable_instances_c_call` / `python reproduce_bugs.py --bug BUG-CORE-007`

---

#### BUG-CORE-008: T4 Monitor scope filter restricts tracing to script directory, ignoring project packages
- **Unique ID**: `BUG-CORE-008`
- **Severity**: High
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/_bootstrap.py:65`, `src/pytracer/instrumentation/monitor.py:24-38`
- **Root Cause Analysis**:
  In `_bootstrap.py:65`, `Monitor(scope_dir=Path(script).resolve().parent, run_dir=run_dir)` initializes `scope_dir` to the immediate directory of the target script. In `monitor.py:33-38`, `_in_scope()` requires `filename.startswith(self.scope_dir)`.
  When a user runs a benchmark or entrypoint in a subdirectory (e.g. `benchmarks/run.py`), `scope_dir` becomes `.../benchmarks`. All imports of project packages (under `src/` or project root) are rejected by `_in_scope`.
- **Actual Behavior**:
  PEP 669 line monitoring and call tracking are silently skipped for all project modules outside the script directory.
- **Expected Behavior**:
  Scoping covers the project root or current working directory.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_008_monitor_scope_filters_project_packages` / `python reproduce_bugs.py --bug BUG-CORE-008`

---

#### BUG-CORE-009: Missing single-precision Fortran BLAS GEMM (sgemm_, scipy_sgemm_64_) in native shim & census
- **Unique ID**: `BUG-CORE-009`
- **Severity**: Medium
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/instrumentation/native/blas_shim.c:10-187`, `src/pytracer/instrumentation/native/__init__.py:19-20`
- **Root Cause Analysis**:
  In `native/__init__.py`, `_GEMM_SYMBOLS` defines `("cblas_dgemm", "cblas_sgemm", "dgemm_", "scipy_cblas_dgemm64_", "scipy_cblas_sgemm64_", "scipy_dgemm_64_")`.
  In `blas_shim.c`, Fortran wrappers are implemented for `dgemm_`, `dgesv_`, `scipy_dgemm_64_`, and `scipy_dgesv_64_`.
  The single-precision Fortran symbols `sgemm_` and `scipy_sgemm_64_` are omitted from both `_GEMM_SYMBOLS` and `blas_shim.c`.
- **Actual Behavior**:
  Single-precision Fortran GEMM calls (standard in LAPACK/SciPy single-precision operations) are not intercepted by the native shim.
- **Expected Behavior**:
  `sgemm_` and `scipy_sgemm_64_` are interposed and reported in `native_kernels.log`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_009_missing_sgemm_blas_shim` / `python reproduce_bugs.py --bug BUG-CORE-009`

---

#### BUG-CORE-010: Monitor.stop() writes erroneous available: True when monitor tier is disabled
- **Unique ID**: `BUG-CORE-010`
- **Severity**: Low
- **Subsystem**: Subsystem 1: Core Tracing & Instrumentation
- **File & Line Reference**: `src/pytracer/_bootstrap.py:66-72, 90`, `src/pytracer/instrumentation/monitor.py:74-90`
- **Root Cause Analysis**:
  When `instrumentation="patch"` (monitor tier disabled by configuration), `monitor.start()` is not called. However, `monitor.stop()` is unconditionally executed in `_bootstrap.py:90`.
  `monitor.stop()` calls `self._write()`, which writes `monitor.json` with `"available": self.available`. Because `self.available` is initialized to `hasattr(sys, "monitoring")` (True on Python 3.12+), `monitor.json` outputs `available: True` with empty counters.
- **Actual Behavior**:
  `monitor.json` misleadingly reports `available: True` and 0 lines executed when the tier was disabled.
- **Expected Behavior**:
  `monitor.json` reflects `"enabled": False` or omits misleading availability flags.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_core.py::test_bug_core_010_monitor_stop_erroneous_available_true` / `python reproduce_bugs.py --bug BUG-CORE-010`

---

### Subsystem 2: Data Storage, Serialization & Trace Loading/Replay

#### BUG-STORE-001: payload_ref column omitted from events.parquet table
- **Unique ID**: `BUG-STORE-001`
- **Severity**: High
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `src/pytracer/storage/parquet.py:19-52, 55-90`
- **Root Cause Analysis**:
  `TraceEvent` in `pytracer.trace.event` defines `payload_ref: str | None = None` to store the relative path to on-disk array payloads (`arrays/*.npy` or `arrays/*.zarr`). In `parquet.py`, `_COLUMNS` lists 32 schema fields and `_row()` maps attributes from `TraceEvent`. `payload_kind` is mapped, but `payload_ref` was completely omitted from both `_COLUMNS` and `_row()`.
- **Actual Behavior**:
  The generated `events.parquet` table does not contain a `payload_ref` column. Downstream analytical tools (DuckDB, Pandas, Polars) cannot join events with on-disk array payloads.
- **Expected Behavior**:
  `payload_ref` is included in the Parquet schema and populated from `TraceEvent.payload_ref`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_001_parquet_payload_ref_omitted` / `python reproduce_bugs.py --bug BUG-STORE-001`

---

#### BUG-STORE-002: Zarr 3 ContainsArrayError on existing array store causes silent save failure and payload loss
- **Unique ID**: `BUG-STORE-002`
- **Severity**: High
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `src/pytracer/storage/arrays.py:83-87, 93-96`
- **Root Cause Analysis**:
  Under Zarr 3.x (installed via `zarr>=2.18`), calling `zarr.save(path, array)` when the target array directory already exists raises `zarr.errors.ContainsArrayError: An array exists in store ...`.
  In `ArrayStore.maybe_store()`, line 93 wraps the save call in `try...except Exception:`, catching `ContainsArrayError`, incrementing `self.n_skipped`, and returning `None`.
- **Actual Behavior**:
  Subsequent writes to existing array paths silently fail and drop payloads.
- **Expected Behavior**:
  Existing stores are cleanly overwritten or updated without dropping payloads.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_002_zarr3_contains_array_error` / `python reproduce_bugs.py --bug BUG-STORE-002`

---

#### BUG-STORE-003: Brittle EOF truncation detection in iter_events
- **Unique ID**: `BUG-STORE-003`
- **Severity**: Medium
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `src/pytracer/trace/reader.py:34-36`
- **Root Cause Analysis**:
  In `iter_events()`:
  ```python
  raw = Path(path).read_bytes()
  lines = raw.split(b"\n")
  last_index = len(lines) - 1
  for i, line in enumerate(lines):
      ...
      except msgspec.DecodeError as e:
          if i >= last_index - 1:
              truncated = True
              break
          raise PytracerError(f"{path}: corrupt event at line {i + 1}: {e}") from e
  ```
  Trailing newlines inflate `last_index`. If a process crashes and leaves trailing blank bytes (`\n\n`), a truncated final event at `last_index - 2` fails `i >= last_index - 1` and raises an unhandled `PytracerError`. Conversely, on short 2-line files, genuine middle-of-file corruption is falsely masked as a crash truncation.
- **Actual Behavior**:
  Trailing blank lines cause valid crash truncations to crash with `PytracerError`.
- **Expected Behavior**:
  Truncation detection determines whether `DecodeError` occurred on the last non-empty line of the file.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_003_iter_events_trailing_empty_lines` / `python reproduce_bugs.py --bug BUG-STORE-003`

---

#### BUG-STORE-004: Multiple unnamed output events overwrite each other in assemble_calls
- **Unique ID**: `BUG-STORE-004`
- **Severity**: Medium
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `src/pytracer/trace/reader.py:104-108`
- **Root Cause Analysis**:
  In `assemble_calls()`:
  ```python
  elif ev.phase == "output":
      name = ev.arg_name or "Ret"
      rec.outputs[name] = ev.summary
  ```
  If a call produces multiple output events without an explicit `arg_name` (e.g. generator steps or custom instrumenter tiers), subsequent outputs overwrite `rec.outputs["Ret"]`.
- **Actual Behavior**:
  Prior output events are overwritten and lost from the call record.
- **Expected Behavior**:
  Outputs are disambiguated as `Ret0`, `Ret1`, etc.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_004_multiple_unnamed_outputs_overwrite` / `python reproduce_bugs.py --bug BUG-STORE-004`

---

#### BUG-STORE-005: Output events with arg_name=None silently dropped from Perfetto export
- **Unique ID**: `BUG-STORE-005`
- **Severity**: Medium
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `src/pytracer/report/perfetto.py:41-47`
- **Root Cause Analysis**:
  In `_call_spans()`:
  ```python
  elif ev.summary is not None and ev.arg_name:
      span["args"][f"{ev.phase}:{ev.arg_name}"] = {...}
  ```
  `TraceEvent.arg_name` defaults to `None` for standard function outputs. Because `ev.arg_name` is falsy, output event summaries are skipped.
- **Actual Behavior**:
  Function return values are omitted from `span["args"]` in the exported Perfetto trace.
- **Expected Behavior**:
  Output events with `arg_name=None` default to `"Ret"` and are included in the span arguments.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_005_perfetto_arg_name_none_dropped` / `python reproduce_bugs.py --bug BUG-STORE-005`

---

#### BUG-STORE-006: Zarr 2 vs 3 format incompatibilities and phantom numcodecs dependency
- **Unique ID**: `BUG-STORE-006`
- **Severity**: Medium
- **Subsystem**: Subsystem 2: Data Storage & Serialization
- **File & Line Reference**: `pyproject.toml:28, 38-39`, `src/pytracer/storage/arrays.py:10, 83-88`
- **Root Cause Analysis**:
  1. `pyproject.toml` declares `arrays = ["zarr>=2.18", "numcodecs>=0.12"]`. Under Zarr 3.x, `zarr.save()` writes the V3 format (`zarr.json`), which cannot be read back by Zarr 2.x environments.
  2. `numcodecs` is never imported or used anywhere in `src/pytracer/`.
- **Actual Behavior**:
  Trace artifacts saved with Zarr 3 cannot be loaded in Zarr 2 environments; an unused dependency is required.
- **Expected Behavior**:
  Format compatibility is pinned or configured for portability, and phantom dependencies are removed.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_storage.py::test_bug_store_006_zarr_format_numcodecs_dependency` / `python reproduce_bugs.py --bug BUG-STORE-006`

---

### Subsystem 3: Numerical/Statistical Analysis & Visualization Outputs

#### BUG-NUM-001: Complex array in mixed-type runs causes ComplexWarning and falsely reports exact 53-bit stability
- **Unique ID**: `BUG-NUM-001`
- **Severity**: Critical
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/analysis/elementwise.py:28, 65-66`
- **Root Cause Analysis**:
  In `stack_arrays()`:
  ```python
  if arrays[0].dtype.kind == "c":
      arrays = [np.abs(a) for a in arrays]
  ```
  If Run 0 produces real outputs (`float64`) and Run 1 stochastically produces complex outputs (`complex128`), `arrays[0].dtype.kind == "c"` is `False`. The arrays are not transformed with `np.abs`.
  `np.stack(arrays)` promotes the entire array to `complex128`.
  In `elementwise_sig()`:
  ```python
  runs = np.atleast_2d(stack.reshape(stack.shape[0], -1)).astype(np.float64, copy=False)
  ```
  NumPy casts complex to float64, emitting `ComplexWarning: Casting complex values to real discards the imaginary part` and discarding the imaginary part entirely.
  If the real parts match across runs, standard deviation evaluates to `0.0`, resulting in a reported significance of `53.0` bits (exact stability).
- **Actual Behavior**:
  Discards imaginary perturbations and reports perfect 53-bit numerical stability.
- **Expected Behavior**:
  If any array is complex, absolute magnitudes are computed across all arrays (`[np.abs(a) if a.dtype.kind == "c" else a for a in arrays]`), or the complex divergence is reported as severe instability.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_num_001_complex_mixed_runs_discard_imag` / `python reproduce_bugs.py --bug BUG-NUM-001`

---

#### BUG-NUM-002: Total non-finite outputs (all-NaN/all-Inf) bypass CI threshold gating completely
- **Unique ID**: `BUG-NUM-002`
- **Severity**: Critical
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/analysis/aggregate.py:184-187`, `src/pytracer/analysis/check.py:110-124`
- **Root Cause Analysis**:
  In `aggregate.py`:
  `nan_var = len({s.nan_count for s in summaries}) > 1`
  If all runs output NaNs, the count does not vary across runs (`len({N}) == 1`), so `nan_instability` evaluates to `False`. When all outputs are NaN, `mean` is `None` and `min_output_sig_bits` is `None`.
  In `check.py`:
  `if min_sig is not None and sig is not None and sig < min_sig:`
  `if not limits.get("allow_nan", True) and row.get("nan_instability"):`
  Because `sig is None`, the significance check does not fire. Because `nan_instability` is `False`, the `allow_nan` check does not fire.
- **Actual Behavior**:
  Algorithms producing 100% NaNs generate zero violations in `pytracer check` and exit with code 0.
- **Expected Behavior**:
  100% NaN outputs trigger violations when `allow_nan=False` or `min_sig_bits` is set.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_num_002_all_nan_bypasses_check_experiment` / `python reproduce_bugs.py --bug BUG-NUM-002`

---

#### BUG-NUM-003: Sporadic NaN runs are silently dropped by sig_bits, masking instability as exact 53-bit precision
- **Unique ID**: `BUG-NUM-003`
- **Severity**: High
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/analysis/aggregate.py:36, 177-180`
- **Root Cause Analysis**:
  In `sig_bits()`:
  ```python
  clean = [v for v in values if v is not None and math.isfinite(v)]
  ```
  If 2 runs produce `5.0` and 1 run produces `NaN`, `clean = [5.0, 5.0]`. The variance of `clean` is `0.0`, so `sig_bits` returns `53.0`.
- **Actual Behavior**:
  Sporadic NaNs are silently dropped; the function is reported as achieving perfect 53-bit precision with 0.0 amplification loss.
- **Expected Behavior**:
  Sporadic NaNs severely downgrade the significance score (to 0.0 bits) and flag instability.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_num_003_sporadic_nan_silently_dropped_sig_bits` / `python reproduce_bugs.py --bug BUG-NUM-003`

---

#### BUG-NUM-004: Dashboard diff_with ignores control-flow divergence regressions
- **Unique ID**: `BUG-NUM-004`
- **Severity**: Medium
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/analysis/diff.py:25-30` vs `src/pytracer/dashboard/data.py:472-487`
- **Root Cause Analysis**:
  In CLI diff (`pytracer.analysis.diff`), `regressed()` checks both precision drops and control-flow divergence (`divergence_b > divergence_a + 1e-12`). In contrast, `dashboard/data.py:diff_with()` only checks `delta_sig < -3.0`, completely ignoring control-flow divergence changes.
- **Actual Behavior**:
  Control-flow divergence regressions flagged by the CLI are marked as `"stable"` in the dashboard.
- **Expected Behavior**:
  Dashboard diff and CLI diff use consistent regression criteria.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_num_004_dashboard_diff_ignores_divergence` / `python reproduce_bugs.py --bug BUG-NUM-004`

---

#### BUG-NUM-005: Exact float equality comparison triggers spurious divergence warnings on machine epsilon differences
- **Unique ID**: `BUG-NUM-005`
- **Severity**: Low
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/analysis/diff.py:83`
- **Root Cause Analysis**:
  In `format_diff()`, line 83 checks `if row.divergence_b != row.divergence_a: note = (note + " divergence-change").strip()`. `divergence_score` is a float ratio `(groups - matched) / groups`. Roundoff error can cause 1-ULP differences between runs that executed identical paths.
- **Actual Behavior**:
  Spurious `"divergence-change"` notes are emitted on machine epsilon differences.
- **Expected Behavior**:
  Comparison checks `abs(row.divergence_b - row.divergence_a) > 1e-12`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_num_005_diff_exact_float_comparison` / `python reproduce_bugs.py --bug BUG-NUM-005`

---

#### BUG-VIS-001: Dash DataTable active_cell indexing uses unsorted table data, opening wrong function in Explorer
- **Unique ID**: `BUG-VIS-001`
- **Severity**: High
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/dashboard/callbacks.py:275-278`, `src/pytracer/dashboard/layout.py:48-61`
- **Root Cause Analysis**:
  In `callbacks.py:open_in_explorer()`:
  `row_idx = active_cell.get("row")`
  `function = table_data[row_idx].get("function")`
  `table_data` is retrieved from `State("functions-table", "data")`. In Dash DataTable, `active_cell["row"]` is the row index in the sorted/filtered viewport, whereas `State("functions-table", "data")` is the original unsorted dataset.
- **Actual Behavior**:
  Clicking a row in a sorted or filtered table navigates to the wrong function in the Explorer tab.
- **Expected Behavior**:
  The callback uses `derived_viewport_data` or explicit row IDs to look up the selected function.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_vis_001_datatable_active_cell_unsorted_data` / `python reproduce_bugs.py --bug BUG-VIS-001`

---

#### BUG-VIS-002: HTML report does not parse Markdown; dumps raw text into <pre>, rendering CSS styling dead
- **Unique ID**: `BUG-VIS-002`
- **Severity**: Medium
- **Subsystem**: Subsystem 3: Numerical Analysis & Visualization
- **File & Line Reference**: `src/pytracer/report/render.py:151-153`
- **Root Cause Analysis**:
  `render_html()` embeds the output of `render_markdown()` directly into `<pre style="white-space: pre-wrap; font-family: inherit;">{{ markdown }}</pre>`. While lines 140-150 define extensive CSS styling for `table`, `th`, `td`, `code`, and `blockquote`, no HTML elements are ever generated.
- **Actual Behavior**:
  `report.html` renders raw Markdown syntax (`|---|---|---|`, `#`, `>`) inside a pre block; CSS stylesheets are completely unused.
- **Expected Behavior**:
  Markdown is parsed into semantic HTML tags (`<table>`, `<th>`, `<td>`), styled by the stylesheet.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_analysis.py::test_bug_vis_002_html_report_markdown_in_pre` / `python reproduce_bugs.py --bug BUG-VIS-002`

---

### Subsystem 4: Python 3 & Modern Dependency Compatibility

#### BUG-COMPAT-001: Dash 4+ dash_table.DataTable deprecation breaks strict warning compliance
- **Unique ID**: `BUG-COMPAT-001`
- **Severity**: Medium
- **Subsystem**: Subsystem 4: Modern Dependency Compatibility
- **File & Line Reference**: `src/pytracer/dashboard/layout.py:48-56, 499`, `src/pytracer/dashboard/callbacks.py:97, 133`
- **Root Cause Analysis**:
  `dash_table.DataTable` is deprecated in Dash 4.x. Instantiating it emits `DeprecationWarning: The dash_table.DataTable will be removed from the builtin dash components in a future major version.`. Under strict CI warning mode (`-W error::Warning`), tests `test_dashboard_builds` and `test_dashboard_compare_mode` fail immediately.
- **Actual Behavior**:
  Emits deprecation warnings on dashboard initialization, failing strict CI test runs.
- **Expected Behavior**:
  Clean execution without deprecation warnings (migrated to `dash-ag-grid` or warning suppressed).
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_compat.py::test_bug_compat_001_dash_table_deprecation` / `python reproduce_bugs.py --bug BUG-COMPAT-001`

---

#### BUG-COMPAT-002: Missing scikit-learn in pyproject.toml causes permanent test suite skip
- **Unique ID**: `BUG-COMPAT-002`
- **Severity**: Low
- **Subsystem**: Subsystem 4: Modern Dependency Compatibility
- **File & Line Reference**: `pyproject.toml:27-48`, `tests/integration/test_sci_plugins.py:45-57`
- **Root Cause Analysis**:
  `pytracer` implements an sklearn plugin (`src/pytracer/plugins/registry.py`) and includes `test_sklearn_plugin_traces_fit`. However, `scikit-learn` is absent from `pyproject.toml` dependencies and optional extras.
- **Actual Behavior**:
  `test_sklearn_plugin_traces_fit` is permanently skipped in standard test environments.
- **Expected Behavior**:
  `scikit-learn` is included in test or optional dependency groups.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_compat.py::test_bug_compat_002_scikit_learn_omitted_pyproject` / `python reproduce_bugs.py --bug BUG-COMPAT-002`

---

#### BUG-COMPAT-003: pytracer doctor reports Python < 3.12 as WARN instead of FAIL
- **Unique ID**: `BUG-COMPAT-003`
- **Severity**: Low
- **Subsystem**: Subsystem 4: Modern Dependency Compatibility
- **File & Line Reference**: `src/pytracer/cli/doctor.py:33-45`
- **Root Cause Analysis**:
  `pyproject.toml` requires `requires-python = ">=3.12"`. In `doctor.py`, running on Python < 3.12 outputs `WARN` and exits 0, falsely suggesting that Python 3.10/3.11 is supported.
- **Actual Behavior**:
  `doctor` returns `WARN` with exit code 0 on Python < 3.12.
- **Expected Behavior**:
  `doctor` returns `FAIL` with exit code 1 on Python < 3.12.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_compat.py::test_bug_compat_003_doctor_reports_warn_python_lt_312` / `python reproduce_bugs.py --bug BUG-COMPAT-003`

---

### Subsystem 5: CLI Entrypoints, Runner Execution & Configuration

#### BUG-CLI-001: Runner forces script parent directory as working directory, breaking relative file paths
- **Unique ID**: `BUG-CLI-001`
- **Severity**: High
- **Subsystem**: Subsystem 5: CLI & Configuration
- **File & Line Reference**: `src/pytracer/experiment.py:156`
- **Root Cause Analysis**:
  `experiment.py:156` launches the child process with `cwd=str(script_path.parent)`. If a user invokes `pytracer run benchmarks/test.py` from their project root, any relative paths to datasets (e.g. `data/input.csv`) fail with `FileNotFoundError`.
- **Actual Behavior**:
  The child process working directory is hijacked to the script's folder.
- **Expected Behavior**:
  The child process preserves the caller's working directory or allows passing `--cwd`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_cli.py::test_bug_cli_001_runner_forces_script_parent_dir_cwd` / `python reproduce_bugs.py --bug BUG-CLI-001`

---

#### BUG-CLI-002: CLI lacks --config flag, preventing explicit configuration file selection
- **Unique ID**: `BUG-CLI-002`
- **Severity**: Medium
- **Subsystem**: Subsystem 5: CLI & Configuration
- **File & Line Reference**: `src/pytracer/cli/main.py:15-123`, `src/pytracer/cli/main.py:126-129`
- **Root Cause Analysis**:
  `pytracer.config.loader.load_config(path=None)` supports custom file paths, but `build_parser()` in `main.py` defines no `--config` or `-c` argument. `_load_config()` always calls `load_config()` with no arguments.
- **Actual Behavior**:
  Users cannot pass a custom config file path on the CLI.
- **Expected Behavior**:
  `--config PATH` is available on the CLI and forwarded to `load_config()`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_cli.py::test_bug_cli_002_cli_missing_config_flag` / `python reproduce_bugs.py --bug BUG-CLI-002`

---

#### BUG-CLI-003: pytracer check silently passes missing or undefined significance under --min-sig-bits
- **Unique ID**: `BUG-CLI-003`
- **Severity**: High
- **Subsystem**: Subsystem 5: CLI & Configuration
- **File & Line Reference**: `src/pytracer/analysis/check.py:110-114`
- **Root Cause Analysis**:
  In `check_experiment()`, lines 111-112: `sig = row.get("min_output_sig_bits")` and `if min_sig is not None and sig is not None and sig < min_sig:`. If `sig` is `None` (significance undefined or zero finite outputs), `sig is not None` is `False`. The check is skipped.
- **Actual Behavior**:
  Functions with undefined or broken significance silently pass `pytracer check`.
- **Expected Behavior**:
  Undefined significance on numeric functions triggers a violation under `--min-sig-bits`.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_cli.py::test_bug_cli_003_check_passes_none_sig_bits` / `python reproduce_bugs.py --bug BUG-CLI-003`

---

#### BUG-CLI-004: Patcher.resolve_targets fails on class wildcards (Class.*)
- **Unique ID**: `BUG-CLI-004`
- **Severity**: Medium
- **Subsystem**: Subsystem 5: CLI & Configuration
- **File & Line Reference**: `src/pytracer/instrumentation/patcher.py:85-94`
- **Root Cause Analysis**:
  In `_resolve_one()`, when handling wildcards (`*`), `parts[:-1]` is passed to `_import_prefix()`. For class wildcards like `scipy.optimize.OptimizeResult.*`, `parts[:-1]` is `["scipy", "optimize", "OptimizeResult"]`. `_import_prefix` attempts to import the class name as a module prefix, which fails (`used != len(parts) - 1`), recording error `cannot import module ...`.
- **Actual Behavior**:
  Class wildcard targets fail to resolve.
- **Expected Behavior**:
  `_resolve_one()` resolves the module containing the class and discovers all callables on the class matching the pattern.
- **Reproduction Reference**:
  `tests/reproductions/test_reproduce_cli.py::test_bug_cli_004_patcher_fails_on_class_wildcard` / `python reproduce_bugs.py --bug BUG-CLI-004`

---

## 4. Defect Severity & Subsystem Distribution Tables

### 4.1 Defect Severity Cross-Tabulation Matrix

| Subsystem | Critical | High | Medium | Low | Total Defects |
|---|:---:|:---:|:---:|:---:|:---:|
| **Subsystem 1: Core Tracing & Instrumentation** | 0 | 4 | 5 | 1 | **10** |
| **Subsystem 2: Data Storage & Serialization** | 0 | 2 | 4 | 0 | **6** |
| **Subsystem 3: Numerical Analysis & Visualization** | 2 | 2 | 2 | 1 | **7** |
| **Subsystem 4: Modern Dependency Compatibility** | 0 | 0 | 1 | 2 | **3** |
| **Subsystem 5: CLI Entrypoints & Configuration** | 0 | 2 | 2 | 0 | **4** |
| **TOTAL** | **2** | **10** | **14** | **4** | **30** |

---

### 4.2 Defect Inventory by Subsystem

| Bug ID | Subsystem | Severity | Primary Target File & Lines | Summary Description |
|---|---|---|---|---|
| **BUG-CORE-001** | Subsystem 1 | High | `instrumentation/recorder.py:126-138`, `patcher.py:206-216` | Method argument names dropped to Arg0, Arg1 on unbound method calls |
| **BUG-CORE-002** | Subsystem 1 | High | `instrumentation/tracer_array.py:37-45` | T3 TracedArray drops taint tracking on functions returning lists of arrays |
| **BUG-CORE-003** | Subsystem 1 | High | `instrumentation/ufunc.py:59-60`, `recorder.py:218-220` | In-place mutation result is completely lost in TracedUfunc.at |
| **BUG-CORE-004** | Subsystem 1 | Medium | `instrumentation/ufunc.py:42-44` | In-place flag falsely set on positional out=None in TracedUfunc.__call__ |
| **BUG-CORE-005** | Subsystem 1 | Medium | `instrumentation/ufunc.py:47-58` | Ufunc methods (reduce, accumulate, outer) silently drop in-place flag |
| **BUG-CORE-006** | Subsystem 1 | Medium | `trace/summary.py:96-99` | Fortran-contiguous arrays force full array copy during Blake2b fingerprinting |
| **BUG-CORE-007** | Subsystem 1 | Medium | `instrumentation/monitor.py:60-66` | T4 Monitor misclassifies callable class instances as C functions |
| **BUG-CORE-008** | Subsystem 1 | High | `_bootstrap.py:65`, `monitor.py:24-38` | T4 Monitor scope filter restricts tracing to script directory |
| **BUG-CORE-009** | Subsystem 1 | Medium | `instrumentation/native/blas_shim.c:10-187`, `native/__init__.py:19-20` | Missing single-precision Fortran BLAS GEMM (sgemm_, scipy_sgemm_64_) |
| **BUG-CORE-010** | Subsystem 1 | Low | `_bootstrap.py:66-72, 90`, `monitor.py:74-90` | Monitor.stop() writes erroneous available: True when monitor tier disabled |
| **BUG-STORE-001** | Subsystem 2 | High | `storage/parquet.py:19-52, 55-90` | payload_ref column omitted from events.parquet table |
| **BUG-STORE-002** | Subsystem 2 | High | `storage/arrays.py:83-87, 93-96` | Zarr 3 ContainsArrayError causes silent save failure and payload loss |
| **BUG-STORE-003** | Subsystem 2 | Medium | `trace/reader.py:34-36` | Brittle EOF truncation detection in iter_events |
| **BUG-STORE-004** | Subsystem 2 | Medium | `trace/reader.py:104-108` | Multiple unnamed output events overwrite each other in assemble_calls |
| **BUG-STORE-005** | Subsystem 2 | Medium | `report/perfetto.py:41-47` | Output events with arg_name=None silently dropped from Perfetto export |
| **BUG-STORE-006** | Subsystem 2 | Medium | `pyproject.toml:28, 38-39`, `storage/arrays.py:10, 83-88` | Zarr 2 vs 3 format incompatibilities and phantom numcodecs dependency |
| **BUG-NUM-001** | Subsystem 3 | Critical | `analysis/elementwise.py:28, 65-66` | Complex array in mixed-type runs discards imaginary part, reports false 53 bits |
| **BUG-NUM-002** | Subsystem 3 | Critical | `analysis/aggregate.py:184-187`, `check.py:110-124` | Total non-finite outputs (all-NaN/all-Inf) bypass CI threshold gating |
| **BUG-NUM-003** | Subsystem 3 | High | `analysis/aggregate.py:36, 177-180` | Sporadic NaN runs silently dropped by sig_bits, masking instability |
| **BUG-NUM-004** | Subsystem 3 | Medium | `analysis/diff.py:25-30` vs `dashboard/data.py:472-487` | Dashboard diff_with ignores control-flow divergence regressions |
| **BUG-NUM-005** | Subsystem 3 | Low | `analysis/diff.py:83` | Exact float equality comparison triggers spurious divergence warnings |
| **BUG-VIS-001** | Subsystem 3 | High | `dashboard/callbacks.py:275-278`, `layout.py:48-61` | Dash DataTable active_cell indexing uses unsorted table data in Explorer |
| **BUG-VIS-002** | Subsystem 3 | Medium | `report/render.py:151-153` | HTML report does not parse Markdown; dumps raw text into <pre> tag |
| **BUG-COMPAT-001** | Subsystem 4 | Medium | `dashboard/layout.py:48-56, 499`, `callbacks.py:97, 133` | Dash 4+ dash_table.DataTable deprecation breaks strict warning compliance |
| **BUG-COMPAT-002** | Subsystem 4 | Low | `pyproject.toml:27-48`, `tests/integration/test_sci_plugins.py:45-57` | Missing scikit-learn in pyproject.toml causes permanent test suite skip |
| **BUG-COMPAT-003** | Subsystem 4 | Low | `cli/doctor.py:33-45` | pytracer doctor reports Python < 3.12 as WARN instead of FAIL |
| **BUG-CLI-001** | Subsystem 5 | High | `experiment.py:156` | Runner forces script parent directory as working directory |
| **BUG-CLI-002** | Subsystem 5 | Medium | `cli/main.py:15-123`, `cli/main.py:126-129` | CLI lacks --config flag, preventing explicit configuration file selection |
| **BUG-CLI-003** | Subsystem 5 | High | `analysis/check.py:110-114` | pytracer check silently passes missing/undefined significance under --min-sig-bits |
| **BUG-CLI-004** | Subsystem 5 | Medium | `instrumentation/patcher.py:85-94` | Patcher.resolve_targets fails on class wildcards (Class.*) |

---

## 5. Verification Commands and Reproducibility Instructions

### 5.1 Baseline Test Suite Execution
To verify the baseline test suite results:
```bash
./.venv/bin/pytest -v -W default -ra
```
*Expected Result*: 205 collected, 204 passed, 1 skipped (`test_sklearn_plugin_traces_fit`), 0 failed, 5 warnings (11 un-deduplicated).

### 5.2 Strict Warning Mode Verification
To observe the test failures caused by `dash_table.DataTable` deprecation:
```bash
./.venv/bin/pytest tests/integration/test_dashboard_export.py -W error::DeprecationWarning
```
*Expected Result*: Immediate test failure on `DeprecationWarning: The dash_table.DataTable will be removed from the builtin dash components in a future major version.`.

### 5.3 Automated Reproduction Suite Execution
To execute all reproduction test cases reproducing the 30 cataloged defects:
```bash
./.venv/bin/pytest tests/reproductions/ -v
```
or via the standalone reproduction CLI runner:
```bash
./.venv/bin/python reproduce_bugs.py
```
To run a specific bug reproduction:
```bash
./.venv/bin/python reproduce_bugs.py --bug BUG-CORE-001
./.venv/bin/python reproduce_bugs.py --bug BUG-NUM-001
```

### 5.4 Core Library Preservation Check
To verify that no modifications have been introduced to the original `pytracer` library code:
```bash
git status --porcelain pytracer/
```
*Expected Result*: Empty output (zero files modified, created, or deleted under `pytracer/` or `src/pytracer/`).
