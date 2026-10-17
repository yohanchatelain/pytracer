"""Reproduction tests for Subsystem 3: Numerical & Statistical Analysis & Visualization bugs.

Covers:
- BUG-NUM-001: Complex array causes ComplexWarning and falsely reports 53-bit stability
- BUG-NUM-002: Total non-finite outputs (all-NaN/all-Inf) bypass CI threshold gating
- BUG-NUM-003: Sporadic NaN runs are silently dropped by sig_bits
- BUG-NUM-004: Dashboard diff_with ignores control-flow divergence regressions
- BUG-NUM-005: Exact float equality triggers spurious divergence warnings on machine epsilon
- BUG-VIS-001: Dash DataTable active_cell indexing uses unsorted table data
- BUG-VIS-002: HTML report does not parse Markdown; dumps raw text into <pre>
"""

import json
import tempfile
import warnings
from pathlib import Path

import numpy as np

from pytracer.analysis.aggregate import aggregate
from pytracer.analysis.align import align
from pytracer.analysis.check import Thresholds, check_experiment
from pytracer.analysis.diff import DiffResult, DiffRow, format_diff
from pytracer.analysis.elementwise import elementwise_sig, stack_arrays
from pytracer.dashboard.data import ExperimentData
from pytracer.report.render import render_html
from pytracer.trace.event import NumericSummary, SourceRef
from pytracer.trace.reader import CallRecord


def test_bug_num_001_complex_array_falsely_reports_53_bits():
    """In stack_arrays(), only arrays[0] is checked for complex dtype.

    If run 0 produces real numbers and run 1 produces complex numbers,
    arrays are stacked as complex128. In elementwise_sig(), casting to float64
    emits ComplexWarning and discards the imaginary part entirely.
    If real parts match, standard deviation evaluates to 0.0, falsely reporting
    53.0 bits (exact stability) despite the severe numerical divergence into the complex plane.
    """
    a0 = np.array([1.0, 2.0])
    a1 = np.array([1.0, 2.0 + 1e-4j])  # Perturbed into complex plane

    stack = stack_arrays([a0, a1])
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        sig = elementwise_sig(stack)

    # Expected: significance metric reflects the ~1e-4 variation (e.g. min sig < 30 bits)
    # Actual on buggy code: imaginary part is discarded with ComplexWarning
    assert sig["min"] < 30.0, (
        f"False precision! Complex divergence discarded and reported as exact 53 bits: {sig}"
    )


def test_bug_num_002_all_nan_outputs_bypass_ci_checks():
    """When an algorithm fails with 100% NaNs across all runs, nan_count is identical

    in every run, so nan_instability evaluates to False. Furthermore, min_output_sig_bits
    is None. In check_experiment(), both min_sig_bits and allow_nan checks evaluate to False,
    allowing total calculation breakdown to silently pass CI.
    """
    with tempfile.TemporaryDirectory() as td:
        analysis_dir = Path(td) / "analysis"
        analysis_dir.mkdir()
        (analysis_dir / "function_summary.json").write_text(
            json.dumps(
                [
                    {
                        "function": "scipy.linalg.solve",
                        "divergence_score": 0.0,
                        "min_output_sig_bits": None,
                        "nan_instability": False,
                        "inf_instability": False,
                    }
                ]
            )
        )
        thresholds = Thresholds(min_sig_bits=20.0, allow_nan=False)
        violations = check_experiment(td, thresholds)

        # Expected: at least one violation flagged because algorithm produces 100% NaNs
        # Actual on buggy code: violations is [] (empty), completely bypassing CI
        assert len(violations) > 0, (
            "Total NaN failure bypassed CI check without flagging any violations"
        )


def test_bug_num_003_sporadic_nan_runs_dropped_by_sig_bits():
    """In sig_bits(), non-finite values are filtered out before variance calculation.

    If 2 runs produce identical finite values (e.g. 5.0) and 1 run produces NaN,
    sig_bits() computes variance over [5.0, 5.0], resulting in std=0.0 and returning
    53.0 bits of precision. The function's sporadic breakdown is masked as perfect stability.
    """
    call_ok = CallRecord(
        call_id=0,
        module="m",
        qualname="q",
        tier="t1",
        ufunc_method=None,
        source=SourceRef(file="/x.py", lineno=1),
        occurrence=0,
        inputs={"a": NumericSummary(dtype="float64", shape=(1,), size=1, mean=1.0)},
        outputs={"Ret": NumericSummary(dtype="float64", shape=(1,), size=1, mean=5.0, nan_count=0)},
    )
    call_nan = CallRecord(
        call_id=0,
        module="m",
        qualname="q",
        tier="t1",
        ufunc_method=None,
        source=SourceRef(file="/x.py", lineno=1),
        occurrence=0,
        inputs={"a": NumericSummary(dtype="float64", shape=(1,), size=1, mean=1.0)},
        outputs={
            "Ret": NumericSummary(dtype="float64", shape=(1,), size=1, mean=None, nan_count=1)
        },
    )

    alignment = align(["r0", "r1", "r2"], [[call_ok], [call_ok], [call_nan]])
    result = aggregate(alignment)
    func_row = result.functions[0]

    # Expected: min_output_sig_bits is degraded (e.g. 0.0 bits or penalized) due to NaN
    # Actual on buggy code: min_output_sig_bits is 53.0 (exact precision claimed)
    assert func_row.min_output_sig_bits != 53.0, (
        f"Sporadic NaN run was masked as exact 53 bits precision: {func_row.min_output_sig_bits}"
    )


def test_bug_num_004_dashboard_diff_ignores_control_flow_divergence():
    """In CLI diff (analysis/diff.py), divergence increases are classified as regressions.

    In Dashboard data (dashboard/data.py:ExperimentData.diff_with), only delta_sig is checked,
    completely ignoring control-flow divergence increases and marking them as 'stable'.
    """

    def make_experiment(td, name, div_score):
        p = Path(td) / name
        p.mkdir()
        ana = p / "analysis"
        ana.mkdir()
        (ana / "function_summary.json").write_text(
            json.dumps(
                [
                    {
                        "function": "compute_kernel",
                        "divergence_score": div_score,
                        "min_output_sig_bits": 50.0,
                        "max_amplification_bits": 0.0,
                        "nan_instability": False,
                        "inf_instability": False,
                        "calls": 10,
                    }
                ]
            )
        )
        (ana / "call_signatures.json").write_text("[]")
        (ana / "alignment_stats.json").write_text("{}")
        (p / "metadata.json").write_text("{}")
        runs = p / "runs"
        runs.mkdir()
        run = runs / "run_000"
        run.mkdir()
        (run / "events.jsonl").write_text("")
        (run / "metadata.json").write_text('{"run_id": "run_000"}')
        return p

    with tempfile.TemporaryDirectory() as td:
        exp_a = make_experiment(td, "expA", 0.0)
        exp_b = make_experiment(td, "expB", 0.8)  # Massive divergence increase in B

        data_a = ExperimentData(exp_a)
        data_b = ExperimentData(exp_b)
        diff = data_b.diff_with(data_a)

        # Expected: status is marked as 'regression' on divergence surge from 0.0 to 0.8
        # Actual on buggy code: status is 'stable' because delta_sig is 0.0
        assert diff[0]["status"] == "regression", (
            f"Expected status 'regression' on divergence surge, got: '{diff[0]['status']}'"
        )


def test_bug_num_005_diff_float_exact_comparison_spurious_warnings():
    """In analysis/diff.py:83, format_diff() checks: if row.divergence_b != row.divergence_a:

    note = (note + ' divergence-change').strip()
    Because divergence_score is floating point (e.g. 1/3), 1-ULP roundoff differences
    (~1e-16) trigger spurious 'divergence-change' warnings.
    """
    row = DiffRow(
        function="solver",
        sig_a=45.0,
        sig_b=45.0,
        sig_delta=0.0,
        divergence_a=1.0 / 3.0,
        divergence_b=(1.0 / 3.0) + 1e-16,  # 1-ULP floating point representation noise
    )
    result = DiffResult(rows=[row], only_in_a=[], only_in_b=[])
    formatted = format_diff(result)

    # Expected: 1-ULP machine epsilon difference does not trigger 'divergence-change'
    # Actual on buggy code: exact != triggers 'divergence-change'
    assert "divergence-change" not in formatted, (
        f"Spurious divergence-change note emitted on 1e-16 difference: {formatted}"
    )


def test_bug_vis_001_dashboard_active_cell_indexes_unsorted_table():
    """In callbacks.py:275-278, open_in_explorer retrieves table_data[active_cell['row']].

    active_cell['row'] corresponds to the sorted/filtered viewport, while
    table_data is State('functions-table', 'data') which is the original unsorted list.
    When a user sorts by instability, clicking the worst function opens an unrelated function.
    """
    from pytracer.dashboard.callbacks import resolve_active_table_function

    # Unsorted data in state
    table_data_unsorted = [
        {"function": "numpy.abs", "min_output_sig_bits": 53.0},
        {"function": "scipy.linalg.solve", "min_output_sig_bits": 12.0},
    ]
    viewport_data_sorted = sorted(
        table_data_unsorted, key=lambda r: r["min_output_sig_bits"]
    )
    # In UI, table is sorted by min_output_sig_bits ascending:
    # row 0 displayed: scipy.linalg.solve (worst function)
    # row 1 displayed: numpy.abs
    active_cell = {"row": 0, "column_id": "function"}

    resolved_function = resolve_active_table_function(
        active_cell, table_data_unsorted, viewport_data_sorted
    )

    # Expected: clicking top row in sorted view resolves 'scipy.linalg.solve'
    assert resolved_function == "scipy.linalg.solve", (
        f"Expected 'scipy.linalg.solve', but unsorted index lookup got '{resolved_function}'"
    )


def test_bug_vis_002_html_report_dumps_raw_markdown_into_pre():
    """In render.py:151-153, render_html() injects render_markdown(data) directly into

    <pre style="...">{{ markdown }}</pre>. Despite extensive CSS styling for table/th/td/code,
    no HTML table or heading elements are generated, displaying raw markdown syntax in pre block.
    """
    html = render_html(
        {
            "alignment": {"runs": 1},
            "functions": [],
            "top_unstable": [
                {
                    "function": "numpy.sum",
                    "min_output_sig_bits": 53.0,
                    "max_amplification_bits": 0.0,
                    "divergence_score": 0.0,
                    "nan_instability": False,
                    "inf_instability": False,
                }
            ],
        }
    )

    # Expected: HTML contains structured <table> elements to render formatted reports
    # Actual on buggy code: No <table> tags exist; raw markdown (|---|---|) dumped into <pre>
    assert "<table>" in html, (
        f"Expected <table> in generated HTML report, got raw markdown text: {html[:250]}"
    )
