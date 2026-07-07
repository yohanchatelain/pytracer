"""End-to-end tests through the real CLI in subprocesses."""

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
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def experiment_dir(workdir) -> Path:
    root = workdir / ".pytracer" / "runs"
    dirs = [
        p
        for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    ]
    assert len(dirs) == 1
    return dirs[0]


@pytest.fixture
def workdir(tmp_path):
    for program in PROGRAMS.glob("*.py"):
        shutil.copy(program, tmp_path)
    return tmp_path


def test_deterministic_run_shows_full_stability(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "3",
         "--plugins", "--target", "numpy.sum", "--target", "numpy.linalg.norm"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    exp = experiment_dir(workdir)

    run_dirs = sorted((exp / "runs").iterdir())
    assert [d.name for d in run_dirs] == ["run-000", "run-001", "run-002"]
    for run_dir in run_dirs:
        assert (run_dir / "events.jsonl").is_file()
        assert (run_dir / "metadata.json").is_file()
        assert (run_dir / "events.parquet").is_file()

    alignment = json.loads((exp / "analysis" / "alignment.json").read_text())
    assert alignment["runs"] == 3
    assert alignment["divergent_call_groups"] == 0
    assert alignment["matched_call_groups"] >= 2  # sum + norm

    functions = json.loads((exp / "analysis" / "function_summary.json").read_text())
    by_name = {f["function"]: f for f in functions}
    assert by_name["numpy.sum"]["min_output_sig_bits"] == 53.0  # determinism invariant
    # store_arrays defaults to "auto": element-wise sig is the common case
    assert by_name["numpy.sum"]["sig_basis"] == "element"

    for name in ("report.md", "report.html", "report.json"):
        assert (exp / "report" / name).is_file()
    assert "numpy.sum" in (exp / "report" / "report.md").read_text()
    assert "Pytracer run complete" in proc.stdout


def test_variability_is_detected(workdir):
    proc = run_cli(
        ["run", "random_variability.py", "--repeat", "3",
         "--plugins", "--target", "numpy.mean"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    exp = experiment_dir(workdir)
    functions = json.loads((exp / "analysis" / "function_summary.json").read_text())
    by_name = {f["function"]: f for f in functions}
    # the data differ per run, so numpy.mean outputs cannot be at full precision
    assert by_name["numpy.mean"]["min_output_sig_bits"] < 53.0


def test_control_flow_divergence_reported(workdir):
    # 6 runs of a coin-flip branch: overwhelmingly likely to diverge at least once
    proc = run_cli(
        ["run", "control_flow_divergence.py", "--repeat", "6",
         "--plugins", "--target", "numpy.sum"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    exp = experiment_dir(workdir)
    alignment = json.loads((exp / "analysis" / "alignment.json").read_text())
    assert alignment["runs"] == 6
    # not asserting divergence > 0 (probabilistic); assert the machinery ran
    assert "divergent_calls" in alignment


def test_script_failure_mirrors_exit_code_and_records_exception(workdir):
    proc = run_cli(
        ["run", "exception_case.py", "--repeat", "2",
         "--plugins", "--target", "numpy.linalg.solve"],
        workdir,
    )
    assert proc.returncode != 0
    exp = experiment_dir(workdir)
    meta = json.loads((exp / "runs" / "run-000" / "metadata.json").read_text())
    assert meta["exit_code"] != 0
    assert "LinAlgError" in (meta.get("error") or "")
    events = (exp / "runs" / "run-000" / "events.jsonl").read_text()
    assert '"phase":"exception"' in events.replace(" ", "")


def test_decorator_api_traced_under_run(workdir):
    script = workdir / "decorated.py"
    script.write_text(
        "import numpy as np\n"
        "import pytracer\n"
        "@pytracer.trace_function\n"
        "def solver(x):\n"
        "    return float(np.sum(x))\n"
        "print(solver(np.arange(4.0)))\n"
    )
    proc = run_cli(["run", "decorated.py", "--repeat", "2", "--plugins"], workdir)
    assert proc.returncode == 0, proc.stderr
    exp = experiment_dir(workdir)
    functions = json.loads((exp / "analysis" / "function_summary.json").read_text())
    assert any(f["function"].endswith(".solver") for f in functions)


def test_monitor_census_feeds_coverage(workdir):
    # numpy.sum is called by the script but NOT traced: the T4 census must
    # surface it as an untraced numerical callable.
    proc = run_cli(
        ["run", "simple_numpy.py", "--repeat", "1",
         "--plugins", "--target", "numpy.linalg.norm"],
        workdir,
    )
    assert proc.returncode == 0, proc.stderr
    exp = experiment_dir(workdir)
    coverage = json.loads((exp / "analysis" / "coverage.json").read_text())
    if coverage["monitor_available"]:
        untraced = {e["function"] for e in coverage["untraced_numerical_callables"]}
        assert any("sum" in name for name in untraced)


def test_clean_removes_only_marked_dirs(workdir):
    proc = run_cli(
        ["run", "simple_numpy.py", "--plugins", "--target", "numpy.sum"], workdir
    )
    assert proc.returncode == 0, proc.stderr
    bystander = workdir / ".pytracer" / "runs" / "not-mine"
    bystander.mkdir()
    (bystander / "data.txt").write_text("keep me")

    proc = run_cli(["clean"], workdir)
    assert proc.returncode == 0
    remaining = list((workdir / ".pytracer" / "runs").iterdir())
    assert bystander in remaining
    assert all(not (p / ".pytracer-experiment").exists() for p in remaining if p.is_dir())
