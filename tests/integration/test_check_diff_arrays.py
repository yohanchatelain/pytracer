"""End-to-end: array storage -> element-wise sig -> check/diff/suggest-targets."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROGRAMS = Path(__file__).parent.parent / "programs"

pytestmark = pytest.mark.integration


def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def experiment_dirs(workdir):
    root = workdir / ".pytracer" / "runs"
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    )


@pytest.fixture
def workdir(tmp_path):
    for program in PROGRAMS.glob("*.py"):
        shutil.copy(program, tmp_path)
    return tmp_path


def test_element_wise_sig_pipeline(workdir):
    proc = run_cli(
        ["run", "random_variability.py", "--repeat", "3", "--plugins",
         "--target", "numpy.mean", "--store-arrays", "always"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    (exp,) = experiment_dirs(workdir)

    # arrays stored per run
    for run_dir in sorted((exp / "runs").iterdir()):
        stored = list((run_dir / "arrays").glob("*.npy"))
        assert stored, f"no arrays stored in {run_dir}"

    functions = json.loads((exp / "analysis" / "function_summary.json").read_text())
    by_name = {f["function"]: f for f in functions}
    mean_row = by_name["numpy.mean"]
    assert mean_row["sig_basis"] == "element"
    # per-run data differ (unseeded RNG): element-wise sig must show loss
    assert mean_row["min_output_sig_bits"] < 53.0

    arguments = json.loads((exp / "analysis" / "argument_summary.json").read_text())
    element_rows = [a for a in arguments if a["sig_basis"] == "element"]
    assert element_rows
    assert any(a["sig_min_bits"] is not None for a in element_rows)

    report = (exp / "report" / "report.md").read_text()
    assert "element-wise" in report


def test_deterministic_element_wise_full_precision(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "3", "--plugins",
         "--target", "numpy.sum", "--store-arrays", "always"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    (exp,) = experiment_dirs(workdir)
    functions = json.loads((exp / "analysis" / "function_summary.json").read_text())
    by_name = {f["function"]: f for f in functions}
    assert by_name["numpy.sum"]["sig_basis"] == "element"
    assert by_name["numpy.sum"]["min_output_sig_bits"] == 53.0


def test_check_command_pass_and_fail(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "2", "--plugins",
         "--target", "numpy.sum"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    (exp,) = experiment_dirs(workdir)

    passing = run_cli(["check", str(exp), "--min-sig-bits", "20"], workdir)
    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert "PASS" in passing.stdout

    failing = run_cli(["check", str(exp), "--min-sig-bits", "60"], workdir)
    assert failing.returncode == 1
    assert "FAIL" in failing.stdout and "numpy.sum" in failing.stdout

    no_thresholds = run_cli(["check", str(exp)], workdir)
    assert no_thresholds.returncode == 2


def test_check_thresholds_file_autoloaded(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "2", "--plugins",
         "--target", "numpy.sum"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    (exp,) = experiment_dirs(workdir)
    (workdir / "pytracer-thresholds.toml").write_text("min_sig_bits = 60\n")
    failing = run_cli(["check", str(exp)], workdir)
    assert failing.returncode == 1


def test_diff_command(workdir):
    for _ in range(2):
        proc = run_cli(
            ["run", "simple_numpy.py", "--repeat", "2", "--plugins",
             "--target", "numpy.sum"],
            workdir,
        )
        assert proc.returncode == 0, proc.stderr
    a, b = experiment_dirs(workdir)
    proc = run_cli(["diff", str(a), str(b), "--fail-on-regression"], workdir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no regressions" in proc.stdout
    assert "numpy.sum" in proc.stdout


def test_suggest_targets_command(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "1", "--plugins",
         "--target", "numpy.linalg.norm"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    (exp,) = experiment_dirs(workdir)
    proc = run_cli(["suggest-targets", str(exp)], workdir)
    coverage = json.loads((exp / "analysis" / "coverage.json").read_text())
    if coverage["monitor_available"]:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "targets = [" in proc.stdout
        assert "sum" in proc.stdout
    else:
        assert proc.returncode == 1
