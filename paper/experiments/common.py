"""Shared helpers for the paper's experiment scripts.

Every experiment runs pytracer in a scratch working directory (so no
.pytracer/ directories pollute the repository), parses the analysis
artifacts, and writes one CSV into paper/results/.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAPER = Path(__file__).resolve().parent.parent
REPO = PAPER.parent
RESULTS = PAPER / "results"
EXAMPLES = REPO / "examples"
PROGRAMS = REPO / "tests" / "programs"
VENV_PY = REPO / ".venv-paper" / "bin" / "python"


def run_pytracer(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pytracer.cli.main", *args],
        cwd=cwd, capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"pytracer {' '.join(args)} failed ({proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


def experiment_dirs(workdir: Path) -> list[Path]:
    """All experiment directories under workdir/.pytracer/runs, oldest first."""
    root = workdir / ".pytracer" / "runs"
    dirs = [
        p for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    ]
    return sorted(dirs, key=lambda p: p.name)


def latest_experiment(workdir: Path) -> Path:
    return experiment_dirs(workdir)[-1]


def load_analysis(exp: Path, name: str):
    return json.loads((exp / "analysis" / f"{name}.json").read_text())


def function_summary(exp: Path) -> dict[str, dict]:
    return {row["function"]: row for row in load_analysis(exp, "function_summary")}


def scratch_with(*scripts: Path) -> Path:
    """Create a scratch dir containing copies of the given scripts."""
    workdir = Path(tempfile.mkdtemp(prefix="pytracer-paper-"))
    for script in scripts:
        shutil.copy(script, workdir)
    return workdir


def write_csv(name: str, rows: list[dict]) -> Path:
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / name
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out.relative_to(REPO)} ({len(rows)} rows)")
    return out


def read_csv(name: str) -> list[dict]:
    with (RESULTS / name).open() as fh:
        return list(csv.DictReader(fh))


def env_info() -> dict:
    import platform
    out = subprocess.run(
        [str(VENV_PY), "-c",
         "import numpy, scipy, sklearn;"
         "print(numpy.__version__, scipy.__version__, sklearn.__version__)"],
        capture_output=True, text=True,
    ).stdout.split()
    return {
        "python": subprocess.run([str(VENV_PY), "--version"],
                                 capture_output=True, text=True).stdout.strip(),
        "numpy": out[0], "scipy": out[1], "sklearn": out[2],
        "platform": platform.platform(),
        "cpu": platform.processor() or "unknown",
    }


def main_guard(fn):
    if not VENV_PY.exists():
        sys.exit(f"missing venv python: {VENV_PY} (see paper/README.md)")
    sys.exit(fn())
