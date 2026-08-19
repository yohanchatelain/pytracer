"""E1 — Detection efficacy on the numerical-pathology gallery.

For each of the 8 classical pathologies in examples/, run the paired
unstable/stable script under pytracer (--repeat 5, unseeded-RNG input
perturbation) and record min_output_sig_bits, amplification, and the
rank of the unstable variant in top_unstable.json.
"""

from __future__ import annotations

import shutil

from common import (
    EXAMPLES,
    function_summary,
    latest_experiment,
    load_analysis,
    main_guard,
    run_pytracer,
    scratch_with,
    write_csv,
)

# (script, unstable function, stable function, min gap asserted by CI)
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

REPEAT = 5


def run() -> int:
    summaries: dict[str, dict] = {}
    for script in sorted({g[0] for g in GALLERY}):
        workdir = scratch_with(EXAMPLES / script)
        run_pytracer(["run", script, "--repeat", str(REPEAT), "--plugins",
                      "--store-arrays", "always"], cwd=workdir)
        exp = latest_experiment(workdir)
        summaries[script] = {
            "functions": function_summary(exp),
            "ranking": [r["function"] for r in load_analysis(exp, "top_unstable")],
        }
        shutil.rmtree(workdir)

    rows = []
    for script, unstable, stable, min_gap in GALLERY:
        funcs = summaries[script]["functions"]
        ranking = summaries[script]["ranking"]
        u, s = funcs[unstable], funcs[stable]
        rows.append({
            "script": script,
            "unstable": unstable.removeprefix("__main__."),
            "stable": stable.removeprefix("__main__."),
            "sig_unstable_bits": round(u["min_output_sig_bits"], 2),
            "sig_stable_bits": round(s["min_output_sig_bits"], 2),
            "gap_bits": round(s["min_output_sig_bits"] - u["min_output_sig_bits"], 2),
            "ci_min_gap": min_gap,
            "amp_unstable_bits": round(u["max_amplification_bits"], 2),
            "amp_stable_bits": round(s["max_amplification_bits"], 2),
            "rank_unstable": ranking.index(unstable) + 1,
            "rank_stable": ranking.index(stable) + 1 if stable in ranking else "",
            "sig_basis": u["sig_basis"],
            "detected": u["min_output_sig_bits"] < s["min_output_sig_bits"] - min_gap,
        })

    write_csv("e1_gallery.csv", rows)
    n_ok = sum(r["detected"] for r in rows)
    n_rank = sum(
        1 for r in rows
        if r["rank_stable"] == "" or r["rank_unstable"] < r["rank_stable"]
    )
    print(f"detected {n_ok}/{len(rows)} pathologies; "
          f"unstable ranked above stable in {n_rank}/{len(rows)}")
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    main_guard(run)
