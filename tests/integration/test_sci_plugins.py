"""scipy/sklearn plugins against the real libraries (skipped when absent)."""

import importlib.util
import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def run_experiment(tmp_path, script_body, extra_args):
    script = tmp_path / "prog.py"
    script.write_text(script_body)
    proc = subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", "run", "prog.py",
         "--repeat", "2", *extra_args],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    root = tmp_path / ".pytracer" / "runs"
    (exp,) = [
        p for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    ]
    return json.loads((exp / "analysis" / "function_summary.json").read_text())


@pytest.mark.skipif(importlib.util.find_spec("scipy") is None, reason="scipy not installed")
def test_scipy_plugin_traces_solve(tmp_path):
    functions = run_experiment(
        tmp_path,
        "import numpy as np\nimport scipy.linalg\n"
        "x = scipy.linalg.solve(np.eye(4) * 2.0, np.ones(4))\n"
        "print(float(x.sum()))\n",
        ["--plugins", "scipy"],
    )
    names = {f["function"] for f in functions}
    assert "scipy.linalg._basic.solve" in names or any(
        n.endswith(".solve") for n in names
    )


@pytest.mark.skipif(importlib.util.find_spec("sklearn") is None, reason="sklearn not installed")
def test_sklearn_plugin_traces_fit(tmp_path):
    functions = run_experiment(
        tmp_path,
        "import numpy as np\nfrom sklearn.decomposition import PCA\n"
        "rng = np.random.default_rng(0)\n"
        "X = rng.standard_normal((50, 5))\n"
        "PCA(n_components=2).fit(X)\nprint('done')\n",
        ["--plugins", "sklearn"],
    )
    names = {f["function"] for f in functions}
    assert any("PCA.fit" in n for n in names), names
