"""Reproduction tests for Subsystem 5: CLI Entrypoints & Runner Execution bugs.

Covers:
- BUG-CLI-001: Runner forces script parent directory as cwd, breaking relative paths
- BUG-CLI-002: CLI lacks --config flag, preventing explicit configuration file selection
- BUG-CLI-003: pytracer check silently passes missing/undefined significance
- BUG-CLI-004: Patcher.resolve_targets fails on class wildcards (Class.*)
"""

import json
import os
import tempfile
from pathlib import Path

from pytracer.analysis.check import Thresholds, check_experiment
from pytracer.cli.main import build_parser
from pytracer.config.schema import PytracerConfig
from pytracer.experiment import run_experiment
from pytracer.instrumentation.patcher import resolve_targets


def test_bug_cli_001_runner_forces_script_dir_as_cwd():
    """In experiment.py:156, subprocess.run() specifies cwd=str(script_path.parent).

    When a user executes pytracer run benchmarks/suite/run.py from the project root,
    the child process cwd is overridden to benchmarks/suite/, causing any relative file paths
    (data inputs, config files, output logs) referenced relative to project root to break.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        script = scripts_dir / "target_script.py"
        cwd_record_file = root / "recorded_cwd.txt"

        script.write_text(
            f"import os, pathlib\npathlib.Path(r'{cwd_record_file}').write_text(os.getcwd())\n"
        )

        cfg = PytracerConfig()
        cfg.trace.plugins = []
        cfg.storage.output_dir = str(root / "out")

        # Run experiment from working directory `root`
        old_cwd = os.getcwd()
        os.chdir(root)
        try:
            run_experiment(
                config=cfg,
                script=str(script),
                script_args=[],
                target_specs=[],
                repeat=1,
                continue_on_error=True,
            )
        finally:
            os.chdir(old_cwd)

        assert cwd_record_file.is_file(), "Child process failed to execute"
        recorded_cwd = cwd_record_file.read_text().strip()

        # Expected: child process preserves the caller's working directory (`root`)
        # Actual on buggy code: child process cwd is forced to script parent (`scripts_dir`)
        assert recorded_cwd == str(root), (
            f"Expected cwd '{root}', but runner forced cwd to script parent '{recorded_cwd}'"
        )


def test_bug_cli_002_cli_lacks_config_flag():
    """In cli/main.py, build_parser() does not define a --config flag, and _load_config()

    does not take an argument, preventing users from passing custom config files
    (e.g. pytracer run script.py --config /path/to/custom_pytracer.toml).
    """
    parser = build_parser()
    try:
        args = parser.parse_args(["run", "dummy.py", "--config", "custom_config.toml"])
        # Expected: parser recognizes --config and stores the path
        assert hasattr(args, "config"), "Parsed arguments missing config attribute"
        assert args.config == "custom_config.toml"
    except SystemExit as exc:
        # Actual on buggy code: argparse raises unrecognized arguments: --config
        raise AssertionError(
            f"CLI parser failed with code {exc.code} on --config flag (unrecognized argument)"
        ) from exc


def test_bug_cli_003_check_passes_missing_sig_bits():
    """In analysis/check.py:112, the check is:

    if min_sig is not None and sig is not None and sig < min_sig:
    If a function has min_output_sig_bits = None (e.g. unmeasured or NaN values),
    sig is not None is False, silently passing check despite --min-sig-bits threshold.
    """
    with tempfile.TemporaryDirectory() as td:
        analysis_dir = Path(td) / "analysis"
        analysis_dir.mkdir()
        (analysis_dir / "function_summary.json").write_text(
            json.dumps(
                [
                    {
                        "function": "unmeasured_func",
                        "divergence_score": 0.0,
                        "min_output_sig_bits": None,
                        "nan_instability": False,
                        "inf_instability": False,
                    }
                ]
            )
        )
        thresholds = Thresholds(min_sig_bits=30.0)
        violations = check_experiment(td, thresholds)

        # Expected: undefined significance is flagged as violation under --min-sig-bits
        # Actual on buggy code: 0 violations returned (silent pass)
        assert len(violations) > 0, (
            "check_experiment silently passed function with min_output_sig_bits=None"
        )


def test_bug_cli_004_patcher_fails_on_class_wildcards():
    """In patcher.py:91-94, _resolve_one() splits wildcard specs by '.' and calls

    _import_prefix(parts[:-1]). If a class wildcard is provided (e.g.
    pytracer.instrumentation.recorder.Recorder.*), parts[:-1] includes the class name.
    Because a class is not an importable module, _import_prefix fails and adds an error:
    "cannot import module '...Recorder'".
    """
    spec = "pytracer.instrumentation.recorder.Recorder.*"
    report = resolve_targets([spec])

    # Expected: methods of Recorder are resolved (len(report.resolved) > 0) with 0 errors
    # Actual on buggy code: len(report.resolved) == 0 and errors contains "cannot import module"
    assert len(report.resolved) > 0, (
        f"Failed to resolve class wildcard {spec}. Errors: {report.errors}"
    )
    assert len(report.errors) == 0, (
        f"Unexpected resolution errors for class wildcard {spec}: {report.errors}"
    )
