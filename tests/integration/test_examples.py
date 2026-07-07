"""The examples gallery doubles as a detection regression suite.

For every classical pathology in examples/, pytracer must (a) run it clean,
(b) measure the unstable variant at substantially fewer significant bits
than its stable twin, and (c) rank the unstable variant above the stable
one. If pytracer stops detecting a textbook instability, this fails.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent.parent / "examples"

pytestmark = pytest.mark.integration

# (script, unstable function, stable function, minimum bit gap)
GALLERY = [
    ("cancellation.py", "__main__.naive_variance", "__main__.stable_variance", 3.0),
    ("quadratic_roots.py", "__main__.naive_small_root", "__main__.stable_small_root", 10.0),
    ("summation_order.py", "__main__.naive_running_sum", "__main__.exact_fsum", 3.0),
    ("ill_conditioned_solve.py", "__main__.solve_hilbert",
     "__main__.solve_well_conditioned", 10.0),
    ("finite_differences.py", "__main__.forward_diff_tiny_h",
     "__main__.central_diff_optimal_h", 5.0),
    ("expm1_log1p.py", "__main__.naive_expm1", "__main__.library_expm1", 5.0),
    ("expm1_log1p.py", "__main__.naive_log1p", "__main__.library_log1p", 5.0),
    ("polynomial_eval.py", "__main__.expanded_poly", "__main__.factored_poly", 10.0),
]


@pytest.fixture(scope="module")
def summaries(tmp_path_factory):
    """Run each example once (repeat=5) and cache its function summary."""
    results: dict[str, dict] = {}
    for script in sorted({g[0] for g in GALLERY}):
        workdir = tmp_path_factory.mktemp(script.replace(".py", ""))
        shutil.copy(EXAMPLES / script, workdir)
        proc = subprocess.run(
            [sys.executable, "-m", "pytracer.cli.main", "run", script,
             "--repeat", "5", "--plugins"],
            cwd=workdir, capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"{script}: {proc.stderr}"
        root = workdir / ".pytracer" / "runs"
        (exp,) = [
            p for p in root.iterdir()
            if p.is_dir() and not p.is_symlink()
            and (p / ".pytracer-experiment").exists()
        ]
        functions = json.loads(
            (exp / "analysis" / "function_summary.json").read_text()
        )
        results[script] = {
            "functions": {f["function"]: f for f in functions},
            "top": json.loads((exp / "analysis" / "top_unstable.json").read_text()),
        }
    return results


@pytest.mark.parametrize(
    ("script", "unstable", "stable", "min_gap"),
    GALLERY,
    ids=[f"{g[0]}::{g[1].split('.')[-1]}" for g in GALLERY],
)
def test_pathology_detected(summaries, script, unstable, stable, min_gap):
    functions = summaries[script]["functions"]
    assert unstable in functions, f"{unstable} not traced; got {sorted(functions)}"
    assert stable in functions, f"{stable} not traced; got {sorted(functions)}"

    sig_unstable = functions[unstable]["min_output_sig_bits"]
    sig_stable = functions[stable]["min_output_sig_bits"]
    assert sig_unstable is not None and sig_stable is not None
    assert sig_unstable < sig_stable - min_gap, (
        f"{script}: expected {unstable} ({sig_unstable:.1f} bits) at least "
        f"{min_gap} bits below {stable} ({sig_stable:.1f} bits)"
    )


@pytest.mark.parametrize(
    ("script", "unstable", "stable", "min_gap"),
    GALLERY,
    ids=[f"{g[0]}::{g[1].split('.')[-1]}::rank" for g in GALLERY],
)
def test_pathology_ranked_above_stable(summaries, script, unstable, stable, min_gap):
    ranking = [row["function"] for row in summaries[script]["top"]]
    assert unstable in ranking
    if stable in ranking:
        assert ranking.index(unstable) < ranking.index(stable), (
            f"{script}: {unstable} ranked below {stable}: {ranking}"
        )
