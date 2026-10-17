"""Reproduction tests for Subsystem 4: Python 3 & Modern Dependency Compatibility bugs.

Covers:
- BUG-COMPAT-001: Dash 4+ dash_table.DataTable deprecation breaks strict warning compliance
- BUG-COMPAT-002: Missing scikit-learn in pyproject.toml causes permanent test suite skip
- BUG-COMPAT-003: pytracer doctor reports Python < 3.12 as WARN instead of FAIL
"""

import importlib.util
import sys
import tomllib
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from pytracer.cli import doctor


@pytest.mark.skipif(importlib.util.find_spec("dash") is None, reason="dash not installed")
def test_bug_compat_001_dash_table_deprecation_strict_warnings():
    """In Dash 4.x, dash_table.DataTable is formally deprecated in favor of dash-ag-grid.

    Initializing dash_table.DataTable via pytracer's data_table helper must not emit
    DeprecationWarning under strict warning compliance (-W error::DeprecationWarning).
    """
    from dash import dash_table

    from pytracer.dashboard.layout import data_table

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _ = data_table(dash_table, [], [], "test-table")
        dep_warnings = [w for w in recorded if issubclass(w.category, DeprecationWarning)]

    # Expected: No DeprecationWarning emitted when building dashboard UI components
    assert len(dep_warnings) == 0, (
        f"data_table emitted {len(dep_warnings)} deprecation warning(s): "
        f"{[str(w.message) for w in dep_warnings]}"
    )


def test_bug_compat_002_missing_sklearn_in_pyproject_toml():
    """pytracer contains a built-in scikit-learn plugin and an integration test

    (test_sklearn_plugin_traces_fit). However, scikit-learn is not declared in
    pyproject.toml under dependencies or any optional-dependencies group ([all], [dev]).
    Standard test installations permanently skip the sklearn test.
    """
    pyproject_data = tomllib.loads(Path("pyproject.toml").read_text())
    deps = pyproject_data.get("project", {}).get("dependencies", [])
    opt_deps = pyproject_data.get("project", {}).get("optional-dependencies", {})

    all_declared = set(deps)
    for group in opt_deps.values():
        all_declared.update(group)

    has_sklearn = any("scikit-learn" in d or "sklearn" in d for d in all_declared)
    # Expected: scikit-learn is declared in optional dependencies for plugin coverage
    # Actual on buggy code: scikit-learn is completely missing from pyproject.toml
    assert has_sklearn is True, (
        "scikit-learn is missing from pyproject.toml dependencies and optional-dependencies"
    )


def test_bug_compat_003_doctor_reports_python_under_312_as_warn():
    """pyproject.toml mandates requires-python = '>=3.12'.

    However, pytracer doctor reports Python < 3.12 with status=WARN and exit_code=0,
    falsely implying that running under Python 3.11 is a supported configuration where
    only the T4 monitor is disabled.
    """
    with (
        patch.object(sys, "version_info", (3, 11, 5, "final", 0)),
        patch.object(sys, "version", "3.11.5 (main, Aug 2024)"),
    ):
        checks = doctor.run_checks()
        py_check = next(c for c in checks if c["name"] == "python")
        exit_status = doctor.exit_code(checks)

        # Expected: doctor reports FAIL and nonzero exit code on Python < 3.12
        # Actual on buggy code: py_check['status'] is 'warn' and exit_code is 0
        assert py_check["status"] == doctor.FAIL, (
            f"Expected doctor status FAIL for Python 3.11, got: '{py_check['status']}'"
        )
        assert exit_status != 0, (
            f"Expected nonzero exit code from doctor on Python 3.11, got: {exit_status}"
        )
