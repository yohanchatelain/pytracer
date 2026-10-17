"""Empirical Challenge & Stress Test Suite for Phase 0 Remediation.

This suite challenges and verifies:
1. CLI --config / -c plumbing across root and all subcommands:
   - Permutations of option placement (before/after subcommands, positional args).
   - Non-existent configuration files (graceful error reporting with exit code 1,
     no unhandled tracebacks).
   - Malformed TOML configuration files (proper error reporting with exit code 1).
   - Empty configuration files and directory paths vs file paths.
   - Config flag precedence and script argument separation with '--'.
2. Doctor diagnostic command:
   - Python version matrix (3.10, 3.11, 3.12, 3.13, 3.14) under mock.
   - Exit code evaluation under combinations of OK, WARN, and multiple FAILs.
   - Multi-failure simulation across environment, permissions, and configuration.
3. Packaging and dependency declarations:
   - Absence of phantom numcodecs dependency.
   - Declaration of scikit-learn under plugins and all.
   - Zarr V2 format portability handling in ArrayStore.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from pytracer.cli.doctor import (
    FAIL,
    OK,
    WARN,
    _check,
    check_python,
    exit_code,
    format_checks,
    run_checks,
)
from pytracer.cli.main import build_parser, main
from pytracer.config.loader import load_config
from pytracer.storage.arrays import ArrayStore, load_array

# ==============================================================================
# 1. CLI --config / -c Placement Permutations
# ==============================================================================


@pytest.mark.parametrize(
    "argv",
    [
        ["--config", "cfg.toml", "run", "script.py"],
        ["run", "--config", "cfg.toml", "script.py"],
        ["run", "script.py", "--config", "cfg.toml"],
        ["-c", "cfg.toml", "run", "script.py"],
        ["run", "-c", "cfg.toml", "script.py"],
        ["run", "script.py", "-c", "cfg.toml"],
        ["-c", "cfg.toml", "report", "exp_dir"],
        ["report", "-c", "cfg.toml", "exp_dir"],
        ["report", "exp_dir", "-c", "cfg.toml"],
        ["-c", "cfg.toml", "check", "exp_dir"],
        ["check", "-c", "cfg.toml", "exp_dir"],
        ["check", "exp_dir", "-c", "cfg.toml"],
        ["--config", "cfg.toml", "doctor"],
        ["doctor", "--config", "cfg.toml"],
        ["-c", "cfg.toml", "doctor"],
        ["doctor", "-c", "cfg.toml"],
        ["-c", "cfg.toml", "config", "show"],
        ["config", "-c", "cfg.toml", "show"],
        ["config", "show", "-c", "cfg.toml"],
        ["-c", "cfg.toml", "config", "validate"],
        ["config", "-c", "cfg.toml", "validate"],
        ["config", "validate", "-c", "cfg.toml"],
        ["--config", "cfg.toml", "clean"],
        ["clean", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "diff", "dir_a", "dir_b"],
        ["diff", "--config", "cfg.toml", "dir_a", "dir_b"],
        ["diff", "dir_a", "dir_b", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "suggest-targets", "exp_dir"],
        ["suggest-targets", "--config", "cfg.toml", "exp_dir"],
        ["suggest-targets", "exp_dir", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "dashboard", "exp_dir"],
        ["dashboard", "--config", "cfg.toml", "exp_dir"],
        ["dashboard", "exp_dir", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "export", "exp_dir"],
        ["export", "--config", "cfg.toml", "exp_dir"],
        ["export", "exp_dir", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "plugins", "list"],
        ["plugins", "--config", "cfg.toml", "list"],
        ["plugins", "list", "--config", "cfg.toml"],
        ["--config", "cfg.toml", "init"],
        ["init", "--config", "cfg.toml"],
    ],
)
def test_cli_config_placement_permutations(argv: list[str]):
    """Verify that --config and -c are parsed correctly regardless of placement."""
    parser = build_parser()
    parsed = parser.parse_args(argv)
    assert parsed.config == "cfg.toml"
    assert str(parsed.config_path) == "cfg.toml"


def test_cli_config_precedence():
    """Verify that a subcommand-level --config overrides a root-level --config."""
    parser = build_parser()
    parsed = parser.parse_args(
        ["--config", "root.toml", "run", "script.py", "--config", "sub.toml"]
    )
    assert parsed.config == "sub.toml"
    assert str(parsed.config_path) == "sub.toml"


def test_cli_config_with_script_args_separator(tmp_path):
    """Verify that --config before or after script does not interfere with '--' args."""
    script = tmp_path / "script.py"
    script.write_text("import sys\n")
    cfg = tmp_path / "custom.toml"
    cfg.write_text("[trace]\nplugins = ['numpy']\n")

    # In main(), arguments after '--' are extracted into args.script_args
    ret = main(
        [
            "run",
            str(script),
            "--config",
            str(cfg),
            "--no-report",
            "--",
            "--custom-script-flag",
            "val",
        ]
    )
    assert ret == 0


# ==============================================================================
# 2. Non-existent and Malformed Configuration Files
# ==============================================================================


def test_cli_nonexistent_config_file_graceful_error(capsys):
    """Verify that non-existent config files produce clean error messages and exit code 1."""
    missing = "completely_nonexistent_config_file.toml"

    # Test pytracer run
    ret_run = main(["run", "dummy.py", "--config", missing])
    captured_run = capsys.readouterr()
    assert ret_run == 1
    assert "configuration file not found" in captured_run.err
    assert "Traceback" not in captured_run.err

    # Test pytracer config show
    ret_show = main(["config", "show", "--config", missing])
    captured_show = capsys.readouterr()
    assert ret_show == 1
    assert "configuration file not found" in captured_show.err

    # Test pytracer clean
    ret_clean = main(["clean", "--config", missing])
    captured_clean = capsys.readouterr()
    assert ret_clean == 1
    assert "configuration file not found" in captured_clean.err

    # Test pytracer doctor
    ret_doc = main(["doctor", "--config", missing])
    captured_doc = capsys.readouterr()
    assert ret_doc == 1
    assert "configuration file not found" in captured_doc.out


def test_cli_malformed_toml_graceful_error(tmp_path, capsys):
    """Verify that malformed TOML files produce clean error messages and exit code 1."""
    bad_toml = tmp_path / "invalid.toml"
    bad_toml.write_text("[trace\ninvalid = ")

    ret_show = main(["config", "show", "--config", str(bad_toml)])
    captured_show = capsys.readouterr()
    assert ret_show == 1
    assert "invalid TOML" in captured_show.err
    assert "Traceback" not in captured_show.err

    ret_doc = main(["doctor", "--config", str(bad_toml)])
    captured_doc = capsys.readouterr()
    assert ret_doc == 1
    assert "invalid:" in captured_doc.out


def test_cli_config_empty_file(tmp_path, capsys):
    """An empty TOML file is valid syntax and should load default configuration."""
    empty_toml = tmp_path / "empty.toml"
    empty_toml.write_text("")

    ret = main(["config", "show", "--config", str(empty_toml)])
    captured = capsys.readouterr()
    assert ret == 0
    data = json.loads(captured.out)
    assert data["trace"]["plugins"] == ["numpy"]
    assert data["analysis"]["alignment"] == "callsite"


def test_cli_config_directory_behavior(tmp_path, capsys):
    """Verify loader and doctor behavior when a directory is passed to --config."""
    # Subcase A: Directory containing pytracer.toml
    dir_with_toml = tmp_path / "dir_with"
    dir_with_toml.mkdir()
    (dir_with_toml / "pytracer.toml").write_text("[trace]\nplugins = ['scikit-learn']\n")

    # load_config resolves directory / pytracer.toml
    cfg = load_config(path=dir_with_toml)
    assert cfg.trace.plugins == ["scikit-learn"]

    ret_show = main(["config", "show", "--config", str(dir_with_toml)])
    captured = capsys.readouterr()
    assert ret_show == 0
    data = json.loads(captured.out)
    assert data["trace"]["plugins"] == ["scikit-learn"]

    # Subcase B: Directory without pytracer.toml returns defaults in loader
    dir_without = tmp_path / "dir_without"
    dir_without.mkdir()
    cfg_default = load_config(path=dir_without)
    assert cfg_default.trace.plugins == ["numpy"]


# ==============================================================================
# 3. Doctor Python Version Matrix & Exit Codes
# ==============================================================================


@pytest.mark.parametrize(
    "vinfo,vstr,expected_status,expected_code",
    [
        ((3, 10, 12, "final", 0), "3.10.12 (main, Nov 2023)", FAIL, 1),
        ((3, 11, 0, "final", 0), "3.11.0 (main, Oct 2022)", FAIL, 1),
        ((3, 11, 9, "final", 0), "3.11.9 (main, Apr 2024)", FAIL, 1),
        ((3, 12, 0, "final", 0), "3.12.0 (main, Oct 2023)", OK, 0),
        ((3, 12, 3, "final", 0), "3.12.3 (main, Apr 2024)", OK, 0),
        ((3, 13, 0, "final", 0), "3.13.0 (main, Oct 2024)", OK, 0),
        ((3, 13, 1, "final", 0), "3.13.1 (main, Dec 2024)", OK, 0),
        ((3, 14, 0, "alpha", 1), "3.14.0a1 (main, 2025)", OK, 0),
    ],
)
def test_doctor_python_version_bounds(vinfo, vstr, expected_status, expected_code):
    """Verify Python version check boundary (< 3.12 FAIL, >= 3.12 OK)."""
    with patch.object(sys, "version_info", vinfo), patch.object(sys, "version", vstr):
        res = check_python()
        assert res["name"] == "python"
        assert res["status"] == expected_status
        if expected_status == FAIL:
            assert "unsupported" in res["detail"]
            assert ">= 3.12" in res["detail"]
        else:
            assert res["detail"].startswith("Python 3.")

        checks = [res]
        assert exit_code(checks) == expected_code


@pytest.mark.parametrize(
    "checks,expected_exit",
    [
        ([], 0),
        ([_check("c1", OK, "all ok")], 0),
        ([_check("c1", OK, "all ok"), _check("c2", OK, "also ok")], 0),
        ([_check("c1", OK, "ok"), _check("c2", WARN, "warning only")], 0),
        ([_check("c1", WARN, "warn 1"), _check("c2", WARN, "warn 2")], 0),
        ([_check("c1", FAIL, "fail 1")], 1),
        ([_check("c1", OK, "ok"), _check("c2", FAIL, "fail 1")], 1),
        ([_check("c1", WARN, "warn"), _check("c2", FAIL, "fail 1")], 1),
        ([_check("c1", OK, "ok"), _check("c2", WARN, "warn"), _check("c3", FAIL, "fail 1")], 1),
        ([_check("c1", FAIL, "f1"), _check("c2", FAIL, "f2"), _check("c3", FAIL, "f3")], 1),
    ],
)
def test_doctor_exit_code_logic(checks: list[dict], expected_exit: int):
    """Verify exit_code() returns 1 if and only if at least one FAIL is present."""
    assert exit_code(checks) == expected_exit


def test_doctor_multi_failure_integration(tmp_path):
    """Verify doctor reports multiple failures and formats correctly without crashing."""
    nonexistent_cfg = tmp_path / "does_not_exist.toml"

    with (
        patch.object(sys, "version_info", (3, 11, 0, "final", 0)),
        patch.object(sys, "version", "3.11.0"),
        patch("os.access", return_value=False),
    ):
        checks = run_checks(directory=tmp_path, config_path=nonexistent_cfg)
        fails = [c for c in checks if c["status"] == FAIL]
        assert len(fails) >= 3, f"Expected >= 3 fails, got: {fails}"

        formatted = format_checks(checks)
        assert "x Python 3.11.0 is unsupported" in formatted
        assert "is not writable" in formatted
        assert "configuration file not found" in formatted
        assert exit_code(checks) == 1


# ==============================================================================
# 4. Packaging and Storage Primitives
# ==============================================================================


def test_pyproject_packaging_declarations():
    """Verify pyproject.toml optional-dependencies are normalized."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    opt_deps = pyproject.get("project", {}).get("optional-dependencies", {})

    # 1. scikit-learn is present in plugins and all
    assert "plugins" in opt_deps, "plugins extra missing from optional-dependencies"
    assert any("scikit-learn" in d for d in opt_deps["plugins"])
    assert any("plugins" in d or "scikit-learn" in d for d in opt_deps["all"])

    # 2. numcodecs is removed from arrays and all
    assert not any("numcodecs" in d for d in opt_deps.get("arrays", []))
    assert not any("numcodecs" in d for d in opt_deps.get("all", []))


def test_zarr_v2_storage_format(tmp_path):
    """Verify ArrayStore writes arrays and handles Zarr format correctly."""
    store = ArrayStore(tmp_path, backend="zarr")
    arr = np.arange(10, dtype=np.float64)

    # Store array with zarr backend
    ref = store.maybe_store(1, "output", "ret", arr)
    assert ref is not None
    assert ref.endswith(".zarr")

    zarr_path = tmp_path / ref
    assert zarr_path.exists()

    # Load back and verify values
    loaded = load_array(tmp_path, ref)
    assert loaded is not None
    np.testing.assert_array_equal(loaded, arr)
