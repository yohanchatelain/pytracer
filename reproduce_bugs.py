#!/usr/bin/env python3
"""pytracer Bug Reproduction Suite Runner.

Executes deterministic reproduction test cases for all cataloged defects
against the unmodified pytracer library and outputs a clean tabular report.

Usage:
    python reproduce_bugs.py [OPTIONS]

Options:
    --filter TEXT       Filter tests by Bug ID, subsystem, or keyword
    --severity TEXT     Filter tests by severity (Critical, High, Medium, Low)
    --subsystem NUM     Filter by subsystem number (1, 2, 3, 4, 5)
    --json              Output results in structured JSON format
    --verbose           Display full stack traces and verbose diagnostic output
    --help              Display this help message
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Ensure repository root and src directory are on sys.path
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
REPRODUCTIONS_DIR = REPO_ROOT / "tests" / "reproductions"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(slots=True)
class BugDefinition:
    bug_id: str
    subsystem_num: int
    subsystem_name: str
    severity: str
    title: str
    target_ref: str
    test_file: str
    test_name: str
    root_cause: str
    actual_behavior: str
    expected_behavior: str


@dataclass(slots=True)
class ReproductionResult:
    bug_id: str
    subsystem: str
    severity: str
    title: str
    target_ref: str
    status: str  # REPRODUCED, NOT_REPRODUCED, ERROR
    elapsed_ms: float
    symptom: str
    root_cause: str
    error_trace: str | None = None


# Authoritative catalog of all 30 confirmed pytracer defects
BUG_CATALOG: list[BugDefinition] = [
    # Subsystem 1: Core Tracing & Instrumentation
    BugDefinition(
        bug_id="BUG-CORE-001",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="High",
        title="Method argument names dropped to Arg0, Arg1 on unbound method invocations",
        target_ref="src/pytracer/instrumentation/recorder.py:126-138",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_001_unbound_method_argument_names",
        root_cause=(
            "wrapt strips instance from args when calling unbound methods, causing "
            "inspect.signature.bind() to fail with TypeError and fall back to Arg0, Arg1."
        ),
        actual_behavior="Method parameter names dropped and replaced by Arg0, Arg1 in trace.",
        expected_behavior="Parameter names from method signature are preserved on unbound calls.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-002",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="High",
        title="T3 TracedArray drops taint tracking on functions returning lists of arrays",
        target_ref="src/pytracer/instrumentation/tracer_array.py:37-45",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_002_traced_array_list_taint_loss",
        root_cause=(
            "rewrap() handles ndarray and tuple but omits list, leaving list elements as raw "
            "np.ndarray."
        ),
        actual_behavior="Functions returning lists of ndarrays lose taint tracking.",
        expected_behavior="Lists of ndarrays are recursively wrapped as TracedArray instances.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-003",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="High",
        title="In-place mutation result is completely lost in TracedUfunc.at",
        target_ref="src/pytracer/instrumentation/ufunc.py:59-60",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_003_ufunc_at_mutation_lost",
        root_cause=(
            "TracedUfunc.at delegates with inplace=True, but because np.ufunc.at returns None, "
            "Recorder only emits Ret=None; mutated input array is not captured."
        ),
        actual_behavior="No output captures mutated array post-mutation; trace shows Ret: None.",
        expected_behavior="Mutated array state and numeric summary emitted as an output event.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-004",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Medium",
        title="In-place flag falsely set on positional out=None in TracedUfunc.__call__",
        target_ref="src/pytracer/instrumentation/ufunc.py:42-44",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_004_ufunc_call_positional_out_none_inplace",
        root_cause=(
            "TracedUfunc.__call__ checks len(args) > nin without checking if positional "
            "argument is None."
        ),
        actual_behavior="Calling ufunc(a, b, None) falsely flags call as in-place mutation.",
        expected_behavior="Calls with positional out=None are recognized as non-inplace.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-005",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Medium",
        title="Ufunc methods (reduce, accumulate, outer) silently drop in-place flag",
        target_ref="src/pytracer/instrumentation/ufunc.py:47-58",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_005_ufunc_methods_drop_inplace_flag",
        root_cause=(
            "reduce, accumulate, reduceat, outer call _self_record without passing inplace, "
            "defaulting inplace to False."
        ),
        actual_behavior="Ufunc method calls with out=array are recorded with inplace=False.",
        expected_behavior="In-place flag is True whenever out parameter is provided.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-006",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Medium",
        title="Fortran-contiguous arrays force full array copy during Blake2b fingerprinting",
        target_ref="src/pytracer/trace/summary.py:96-99",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_006_fortran_array_copy_fingerprint",
        root_cause=(
            "array.reshape(-1) defaults to C-order. For Fortran arrays, NumPy cannot make a view "
            "and allocates a complete array copy."
        ),
        actual_behavior="Full memory duplication of large Fortran arrays in RAM, risking OOM.",
        expected_behavior="Zero-copy strided view via ravel(order='K') or reshape(-1, order='F').",
    ),
    BugDefinition(
        bug_id="BUG-CORE-007",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Medium",
        title="T4 Monitor misclassifies callable class instances as C functions",
        target_ref="src/pytracer/instrumentation/monitor.py:60-66",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_007_monitor_callable_instance_as_c_call",
        root_cause=(
            "Monitor.on_call checks hasattr(callable_obj, '__code__'). Callable class instances "
            "store code on __call__, not the instance."
        ),
        actual_behavior="Pure Python callable instances are logged into c_calls as C functions.",
        expected_behavior="Callable instances inspected for __call__.__code__ as Python calls.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-008",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="High",
        title="T4 Monitor scope filter restricts tracing to script directory",
        target_ref="src/pytracer/_bootstrap.py:65",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_008_monitor_scope_filter_excludes_project_packages",
        root_cause=(
            "_bootstrap.py sets scope_dir to script.parent. Sibling package directories in "
            "workspace return False from _in_scope()."
        ),
        actual_behavior="Project package code outside script parent directory ignored by monitor.",
        expected_behavior="Project workspace root or package directories included in scope.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-009",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Medium",
        title="Missing single-precision Fortran BLAS GEMM in native shim & census",
        target_ref="src/pytracer/instrumentation/native/blas_shim.c:10-187",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_009_missing_sgemm_symbols_in_native_shim",
        root_cause=(
            "blas_shim.c and _GEMM_SYMBOLS include dgemm_ and scipy_dgemm_64_ but omit "
            "sgemm_ and scipy_sgemm_64_."
        ),
        actual_behavior="Single-precision Fortran GEMM calls bypass the native census unobserved.",
        expected_behavior="sgemm_ and scipy_sgemm_64_ are interposed and logged by native shim.",
    ),
    BugDefinition(
        bug_id="BUG-CORE-010",
        subsystem_num=1,
        subsystem_name="Core Tracing & Instrumentation",
        severity="Low",
        title="Monitor.stop() writes erroneous available: True when monitor tier is disabled",
        target_ref="src/pytracer/_bootstrap.py:66-72, 90",
        test_file="test_core_bugs.py",
        test_name="test_bug_core_010_monitor_stop_erroneous_available_when_disabled",
        root_cause=(
            "Monitor.stop() unconditionally writes monitor.json with "
            "available=hasattr(sys, 'monitoring') even when monitor was never started."
        ),
        actual_behavior="monitor.json claims available: True with empty counts when disabled.",
        expected_behavior="monitor.json indicates monitor tier was disabled by configuration.",
    ),
    # Subsystem 2: Data Storage & Serialization
    BugDefinition(
        bug_id="BUG-STORE-001",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="High",
        title="payload_ref column omitted from events.parquet table",
        target_ref="src/pytracer/storage/parquet.py:19-52, 55-90",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_001_parquet_payload_ref_omitted",
        root_cause="_COLUMNS schema tuple and _row() mapping in parquet.py omit payload_ref.",
        actual_behavior="Parquet table has no payload_ref column, breaking array links.",
        expected_behavior="events.parquet contains payload_ref string column referencing arrays.",
    ),
    BugDefinition(
        bug_id="BUG-STORE-002",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="High",
        title="Zarr 3 ContainsArrayError causes silent save failure and payload loss",
        target_ref="src/pytracer/storage/arrays.py:83-87, 93-96",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_002_zarr3_contains_array_error_drops_payload",
        root_cause=(
            "In Zarr 3, zarr.save() raises ContainsArrayError if directory exists. "
            "ArrayStore catches and returns None."
        ),
        actual_behavior="Second write to same stem fails silently, incrementing n_skipped.",
        expected_behavior="Existing array store is overwritten cleanly without payload loss.",
    ),
    BugDefinition(
        bug_id="BUG-STORE-003",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="Medium",
        title="Brittle EOF truncation detection in iter_events",
        target_ref="src/pytracer/trace/reader.py:34-36",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_003_brittle_eof_truncation_detection",
        root_cause=(
            "last_index = len(lines) - 1 includes trailing empty lines, causing legitimate "
            "crash truncations to raise PytracerError."
        ),
        actual_behavior="Trailing blank lines cause crash-truncated JSONL to raise PytracerError.",
        expected_behavior="iter_events safely recovers valid events and returns truncated=True.",
    ),
    BugDefinition(
        bug_id="BUG-STORE-004",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="Medium",
        title="Multiple unnamed output events overwrite each other in assemble_calls",
        target_ref="src/pytracer/trace/reader.py:104-108",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_004_unnamed_outputs_overwrite_in_assemble_calls",
        root_cause=(
            "assemble_calls hardcodes name = ev.arg_name or 'Ret'. Unnamed outputs overwrite "
            "outputs['Ret']."
        ),
        actual_behavior="Prior return values from multi-output or generator calls are lost.",
        expected_behavior="Multiple outputs are indexed (Ret0, Ret1) or preserved in a list/dict.",
    ),
    BugDefinition(
        bug_id="BUG-STORE-005",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="Medium",
        title="Output events with arg_name=None silently dropped from Perfetto export",
        target_ref="src/pytracer/report/perfetto.py:41-47",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_005_perfetto_drops_unnamed_output_events",
        root_cause=(
            "_call_spans requires ev.arg_name to be truthy. Output events default to arg_name=None."
        ),
        actual_behavior="Output summaries dropped from span['args'] in exported Perfetto traces.",
        expected_behavior="Output summaries with arg_name=None default to Ret in trace spans.",
    ),
    BugDefinition(
        bug_id="BUG-STORE-006",
        subsystem_num=2,
        subsystem_name="Data Storage & Serialization",
        severity="Medium",
        title="Zarr 2 vs 3 format incompatibilities and phantom numcodecs dependency",
        target_ref="pyproject.toml:28, 38-39",
        test_file="test_storage_bugs.py",
        test_name="test_bug_store_006_phantom_numcodecs_dependency",
        root_cause=(
            "numcodecs is mandated in pyproject.toml [arrays] and [all] but never imported or "
            "used in pytracer."
        ),
        actual_behavior="Phantom dependency forced onto user environments.",
        expected_behavior="Unused dependencies removed from packaging.",
    ),
    # Subsystem 3: Numerical/Statistical Analysis & Visualization
    BugDefinition(
        bug_id="BUG-NUM-001",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="Critical",
        title="Complex array causes ComplexWarning and falsely reports exact 53-bit stability",
        target_ref="src/pytracer/analysis/elementwise.py:28, 65-66",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_num_001_complex_array_falsely_reports_53_bits",
        root_cause=(
            "stack_arrays checks only arrays[0] for complex dtype. Mixed real/complex promotes "
            "to complex, then float64 cast drops imaginary part."
        ),
        actual_behavior="ComplexWarning emitted, imaginary part dropped, 53 bits reported.",
        expected_behavior="Magnitude computed via np.abs or divergence flagged as precision loss.",
    ),
    BugDefinition(
        bug_id="BUG-NUM-002",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="Critical",
        title="Total non-finite outputs (all-NaN/all-Inf) bypass CI threshold gating completely",
        target_ref="src/pytracer/analysis/aggregate.py:184-187",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_num_002_all_nan_outputs_bypass_ci_checks",
        root_cause=(
            "nan_instability requires variance in nan_count across runs. When all runs produce "
            "NaNs, nan_instability is False and min_sig_bits is None."
        ),
        actual_behavior="Total catastrophic NaN failure produces 0 CI violations, passing CI.",
        expected_behavior="100% NaN outputs trigger violations under allow_nan or min_sig_bits.",
    ),
    BugDefinition(
        bug_id="BUG-NUM-003",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="High",
        title="Sporadic NaN runs are silently dropped by sig_bits, masking instability",
        target_ref="src/pytracer/analysis/aggregate.py:36, 177-180",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_num_003_sporadic_nan_runs_dropped_by_sig_bits",
        root_cause=(
            "sig_bits() filters out non-finite values prior to variance calculation: "
            "clean = [v for v in values if math.isfinite(v)]."
        ),
        actual_behavior="Sporadic NaN run is dropped; 2 remaining identical runs yield 53.0 bits.",
        expected_behavior="Instability into NaN penalizes function significance down to 0.0 bits.",
    ),
    BugDefinition(
        bug_id="BUG-NUM-004",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="Medium",
        title="Dashboard diff_with ignores control-flow divergence regressions",
        target_ref="src/pytracer/dashboard/data.py:472-487",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_num_004_dashboard_diff_ignores_control_flow_divergence",
        root_cause=(
            "dashboard/data.py diff_with() checks delta_sig only, ignoring divergence_score deltas."
        ),
        actual_behavior="Massive control-flow divergence increases are labeled as 'stable'.",
        expected_behavior="Control-flow divergence increases categorized as 'regression'.",
    ),
    BugDefinition(
        bug_id="BUG-NUM-005",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="Low",
        title="Exact float equality triggers spurious divergence warnings on machine epsilon",
        target_ref="src/pytracer/analysis/diff.py:83",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_num_005_diff_float_exact_comparison_spurious_warnings",
        root_cause=(
            "format_diff() checks row.divergence_b != row.divergence_a without tolerance, "
            "unlike line 29 which uses 1e-12 tolerance."
        ),
        actual_behavior="1-ULP roundoff noise triggers spurious 'divergence-change' notes.",
        expected_behavior="Floating-point tolerance (abs(b - a) > 1e-12) avoids false alarms.",
    ),
    BugDefinition(
        bug_id="BUG-VIS-001",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="High",
        title="Dash DataTable active_cell indexing uses unsorted table data",
        target_ref="src/pytracer/dashboard/callbacks.py:275-278",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_vis_001_dashboard_active_cell_indexes_unsorted_table",
        root_cause=(
            "active_cell['row'] is the index in the sorted viewport, while table_data is "
            "State('functions-table', 'data') which is unsorted."
        ),
        actual_behavior="Clicking top row in sorted table resolves unrelated function.",
        expected_behavior="Table lookup uses row ID or derived_viewport_data to resolve function.",
    ),
    BugDefinition(
        bug_id="BUG-VIS-002",
        subsystem_num=3,
        subsystem_name="Numerical Analysis & Visualization",
        severity="Medium",
        title="HTML report does not parse Markdown; dumps raw text into <pre>",
        target_ref="src/pytracer/report/render.py:151-153",
        test_file="test_analysis_bugs.py",
        test_name="test_bug_vis_002_html_report_dumps_raw_markdown_into_pre",
        root_cause=(
            "render_html() dumps markdown directly into <pre> without HTML table generation."
        ),
        actual_behavior="HTML report displays raw markdown syntax in pre block; CSS is dead.",
        expected_behavior="Report is rendered with structured HTML tables formatted by CSS.",
    ),
    # Subsystem 4: Python 3 & Modern Dependency Compatibility
    BugDefinition(
        bug_id="BUG-COMPAT-001",
        subsystem_num=4,
        subsystem_name="Python 3 & Dependency Compatibility",
        severity="Medium",
        title="Dash 4+ dash_table.DataTable deprecation breaks strict warning compliance",
        target_ref="src/pytracer/dashboard/layout.py:48-56, 499",
        test_file="test_compat_bugs.py",
        test_name="test_bug_compat_001_dash_table_deprecation_strict_warnings",
        root_cause=(
            "dash_table.DataTable is deprecated in Dash 4+. Initializing emits DeprecationWarning."
        ),
        actual_behavior="Produces 5 DeprecationWarnings; crashes under strict -W error flags.",
        expected_behavior="Warning suppression or migration to dash-ag-grid avoids warnings.",
    ),
    BugDefinition(
        bug_id="BUG-COMPAT-002",
        subsystem_num=4,
        subsystem_name="Python 3 & Dependency Compatibility",
        severity="Low",
        title="Missing scikit-learn in pyproject.toml causes permanent test suite skip",
        target_ref="pyproject.toml:27-48",
        test_file="test_compat_bugs.py",
        test_name="test_bug_compat_002_missing_sklearn_in_pyproject_toml",
        root_cause="scikit-learn is omitted from pyproject.toml dependencies or optional groups.",
        actual_behavior="test_sklearn_plugin_traces_fit is permanently skipped in test runs.",
        expected_behavior="scikit-learn declared in optional-dependencies.plugins or dev.",
    ),
    BugDefinition(
        bug_id="BUG-COMPAT-003",
        subsystem_num=4,
        subsystem_name="Python 3 & Dependency Compatibility",
        severity="Low",
        title="pytracer doctor reports Python < 3.12 as WARN instead of FAIL",
        target_ref="src/pytracer/cli/doctor.py:33-45",
        test_file="test_compat_bugs.py",
        test_name="test_bug_compat_003_doctor_reports_python_under_312_as_warn",
        root_cause=(
            "doctor.py returns WARN on Python < 3.12 with exit code 0, conflicting with "
            "requires-python = '>=3.12'."
        ),
        actual_behavior="doctor passes on unsupported Python versions (< 3.12).",
        expected_behavior="doctor reports FAIL and exits nonzero when run on Python < 3.12.",
    ),
    # Subsystem 5: CLI Entrypoints & Runner Execution
    BugDefinition(
        bug_id="BUG-CLI-001",
        subsystem_num=5,
        subsystem_name="CLI Entrypoints & Runner Execution",
        severity="High",
        title="Runner forces script parent directory as cwd, breaking relative paths",
        target_ref="src/pytracer/experiment.py:156",
        test_file="test_cli_bugs.py",
        test_name="test_bug_cli_001_runner_forces_script_dir_as_cwd",
        root_cause="experiment.py executes subprocess.run with cwd=str(script_path.parent).",
        actual_behavior="Child process cwd forced to script directory, breaking caller paths.",
        expected_behavior="Child process preserves caller working directory.",
    ),
    BugDefinition(
        bug_id="BUG-CLI-002",
        subsystem_num=5,
        subsystem_name="CLI Entrypoints & Runner Execution",
        severity="Medium",
        title="CLI lacks --config flag, preventing explicit configuration file selection",
        target_ref="src/pytracer/cli/main.py:15-123",
        test_file="test_cli_bugs.py",
        test_name="test_bug_cli_002_cli_lacks_config_flag",
        root_cause=(
            "build_parser() does not define a --config flag, and _load_config() does not accept "
            "a path argument."
        ),
        actual_behavior="Passing --config to CLI subcommands exits with unrecognized arguments.",
        expected_behavior="CLI parses --config and loads specified configuration file.",
    ),
    BugDefinition(
        bug_id="BUG-CLI-003",
        subsystem_num=5,
        subsystem_name="CLI Entrypoints & Runner Execution",
        severity="High",
        title="pytracer check silently passes missing/undefined significance under --min-sig-bits",
        target_ref="src/pytracer/analysis/check.py:110-114",
        test_file="test_cli_bugs.py",
        test_name="test_bug_cli_003_check_passes_missing_sig_bits",
        root_cause=(
            "check_experiment() guards min_sig with 'sig is not None'. Undefined significance "
            "evaluates to None."
        ),
        actual_behavior="Functions with undefined significance silently pass --min-sig-bits.",
        expected_behavior="Undefined significance flagged as violations under --min-sig-bits.",
    ),
    BugDefinition(
        bug_id="BUG-CLI-004",
        subsystem_num=5,
        subsystem_name="CLI Entrypoints & Runner Execution",
        severity="Medium",
        title="Patcher.resolve_targets fails on class wildcards (Class.*)",
        target_ref="src/pytracer/instrumentation/patcher.py:85-94",
        test_file="test_cli_bugs.py",
        test_name="test_bug_cli_004_patcher_fails_on_class_wildcards",
        root_cause=(
            "_resolve_one attempts _import_prefix on parts[:-1]. When patching Class.*, "
            "parts[:-1] includes the class name, which cannot be imported as a module."
        ),
        actual_behavior="Target specification Class.* fails with 'cannot import module'.",
        expected_behavior="Class wildcards successfully resolve and patch all methods of class.",
    ),
]

# Module cache for dynamically loaded reproduction files
_LOADED_MODULES: dict[str, Any] = {}


def _get_test_function(test_file: str, test_name: str) -> Callable:
    """Loads test function from file in tests/reproductions using direct file loading."""
    if test_file not in _LOADED_MODULES:
        file_path = REPRODUCTIONS_DIR / test_file
        if not file_path.is_file():
            raise FileNotFoundError(f"Reproduction test file not found: {file_path}")
        mod_name = file_path.stem
        spec = importlib.util.spec_from_file_location(mod_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module spec from {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _LOADED_MODULES[test_file] = module
    else:
        module = _LOADED_MODULES[test_file]

    if not hasattr(module, test_name):
        raise AttributeError(f"Module {test_file} does not have test function {test_name}")
    return getattr(module, test_name)


def run_single_reproduction(bug: BugDefinition, verbose: bool = False) -> ReproductionResult:
    """Executes a single bug reproduction test and confirms the defect manifestation."""
    t0 = time.perf_counter()
    status = "REPRODUCED"
    symptom = ""
    error_trace: str | None = None

    try:
        test_fn = _get_test_function(bug.test_file, bug.test_name)

        out_sink = io.StringIO()
        err_sink = io.StringIO()
        with (
            contextlib.redirect_stdout(out_sink if not verbose else sys.stdout),
            contextlib.redirect_stderr(err_sink if not verbose else sys.stderr),
        ):
            try:
                test_fn()
                # Test passes without raising -> bug is FIXED
                status = "FIXED"
                symptom = f"Verified fixed: {bug.expected_behavior}"
            except AssertionError as exc:
                status = "REPRODUCED"
                msg = str(exc).strip()
                symptom = msg.split("\n")[0] if msg else "AssertionError (defect verified)"
            except BaseException as exc:
                if isinstance(exc, KeyboardInterrupt):
                    raise
                status = "REPRODUCED"
                msg = str(exc).strip()
                symptom = (
                    f"{type(exc).__name__}: {msg.split(chr(10))[0]}" if msg else type(exc).__name__
                )

    except Exception as exc:
        status = "ERROR"
        symptom = f"Harness error importing/running test: {type(exc).__name__}: {exc}"
        error_trace = traceback.format_exc()

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if verbose and error_trace:
        print(f"[{bug.bug_id}] Error trace:\n{error_trace}")

    return ReproductionResult(
        bug_id=bug.bug_id,
        subsystem=bug.subsystem_name,
        severity=bug.severity,
        title=bug.title,
        target_ref=bug.target_ref,
        status=status,
        elapsed_ms=elapsed_ms,
        symptom=symptom,
        root_cause=bug.root_cause,
        error_trace=error_trace,
    )


def print_tabular_report(results: list[ReproductionResult], verbose: bool = False) -> None:
    """Prints a clean ASCII table of cataloged bugs, remediation status, and verification."""
    print("\n" + "=" * 126)
    print(" " * 37 + "PYTRACER BUG REMEDIATION & VERIFICATION REPORT")
    print("=" * 126)

    col_id = "Bug ID"
    col_sub = "Subsystem"
    col_sev = "Severity"
    col_stat = "Status"
    col_time = "Time"
    col_symp = "Verification / Symptom"

    fmt_row = "{:<13} | {:<28} | {:<9} | {:<12} | {:>7} | {}"
    print(fmt_row.format(col_id, col_sub, col_sev, col_stat, col_time, col_symp))
    border = (
        "-" * 13
        + "-+-"
        + "-" * 28
        + "-+-"
        + "-" * 9
        + "-+-"
        + "-" * 12
        + "-+-"
        + "-" * 7
        + "-+-"
        + "-" * 46
    )
    print(border)

    for r in results:
        symp = r.symptom.replace("\n", " ")
        if len(symp) > 46:
            symp = symp[:43] + "..."
        t_str = f"{r.elapsed_ms:.1f}ms"
        print(fmt_row.format(r.bug_id, r.subsystem[:28], r.severity, r.status, t_str, symp))
        if verbose:
            print(f"    Target:     {r.target_ref}")
            print(f"    Root Cause: {r.root_cause}")
            print(f"    Full Note:  {r.symptom}")
            print("    " + "-" * 80)

    print("=" * 126)

    total = len(results)
    fixed = sum(1 for r in results if r.status == "FIXED")
    reproduced = sum(1 for r in results if r.status == "REPRODUCED")
    errors = sum(1 for r in results if r.status == "ERROR")

    crit = sum(1 for r in results if r.severity == "Critical")
    high = sum(1 for r in results if r.severity == "High")
    med = sum(1 for r in results if r.severity == "Medium")
    low = sum(1 for r in results if r.severity == "Low")

    crit_fix = sum(1 for r in results if r.severity == "Critical" and r.status == "FIXED")
    high_fix = sum(1 for r in results if r.severity == "High" and r.status == "FIXED")
    med_fix = sum(1 for r in results if r.severity == "Medium" and r.status == "FIXED")
    low_fix = sum(1 for r in results if r.severity == "Low" and r.status == "FIXED")

    pct = fixed / max(total, 1) * 100
    print("\nSUMMARY STATISTICS:")
    print(f"  Total Bugs Cataloged:    {total}")
    print(f"  Verified Fixed:          {fixed} / {total} ({pct:.1f}%)")
    if reproduced:
        print(f"  Still Failing (Unfixed): {reproduced}")
    if errors:
        print(f"  Harness Errors:          {errors}")

    print("\nSEVERITY BREAKDOWN:")
    print(f"  Critical: {crit:<3} (fixed: {crit_fix}/{crit})")
    print(f"  High:     {high:<3} (fixed: {high_fix}/{high})")
    print(f"  Medium:   {med:<3} (fixed: {med_fix}/{med})")
    print(f"  Low:      {low:<3} (fixed: {low_fix}/{low})")

    print("\nSUBSYSTEM BREAKDOWN:")
    subsystems = [
        "Core Tracing & Instrumentation",
        "Data Storage & Serialization",
        "Numerical Analysis & Visualization",
        "Python 3 & Dependency Compatibility",
        "CLI Entrypoints & Runner Execution",
    ]
    for sub in subsystems:
        sub_res = [r for r in results if r.subsystem == sub]
        sub_fix = sum(1 for r in sub_res if r.status == "FIXED")
        print(f"  - {sub:<36}: {sub_fix}/{len(sub_res)} fixed")
    print("=" * 126 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pytracer Bug Reproduction & Fix Verification Suite Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--filter", "--bug", default=None, help="Filter by Bug ID, subsystem, or keyword"
    )
    parser.add_argument(
        "--severity",
        default=None,
        choices=["Critical", "High", "Medium", "Low"],
        help="Filter by severity",
    )
    parser.add_argument(
        "--subsystem",
        type=int,
        default=None,
        choices=[1, 2, 3, 4, 5],
        help="Filter by subsystem number",
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument(
        "--verbose", action="store_true", help="Display stack traces and reproduction logs"
    )

    args = parser.parse_args()

    candidates = BUG_CATALOG
    if args.subsystem is not None:
        candidates = [b for b in candidates if b.subsystem_num == args.subsystem]
    if args.severity is not None:
        candidates = [b for b in candidates if b.severity.lower() == args.severity.lower()]
    if args.filter:
        query = args.filter.lower()
        candidates = [
            b
            for b in candidates
            if query in b.bug_id.lower()
            or query in b.title.lower()
            or query in b.subsystem_name.lower()
            or query in b.root_cause.lower()
        ]

    if not candidates:
        print(
            f"No bugs matched filter (filter={args.filter}, severity={args.severity}, "
            f"subsystem={args.subsystem})"
        )
        return 0

    results: list[ReproductionResult] = []
    for bug in candidates:
        res = run_single_reproduction(bug, verbose=args.verbose)
        results.append(res)

    if args.json:
        payload = {
            "summary": {
                "total": len(results),
                "fixed": sum(1 for r in results if r.status == "FIXED"),
                "reproduced": sum(1 for r in results if r.status == "REPRODUCED"),
                "errors": sum(1 for r in results if r.status == "ERROR"),
            },
            "results": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        print_tabular_report(results, verbose=args.verbose)

    all_fixed = all(r.status == "FIXED" for r in results)
    return 0 if all_fixed else 1


if __name__ == "__main__":
    sys.exit(main())
