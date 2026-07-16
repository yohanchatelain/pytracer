"""E6 — End-to-end scikit-learn case study and numerical CI.

Traces a StandardScaler + PCA + LogisticRegression pipeline on
near-collinear data (10 repetitions, unseeded-RNG input jitter), records
the most unstable traced calls, then demonstrates the two CI workflows:

* `pytracer check`  — threshold gate (min sig bits / max divergence),
  exit code is the product;
* `pytracer diff`   — A/B comparison of the float64 pipeline against the
  identical pipeline in float32, with --fail-on-regression.
"""

from __future__ import annotations

import json
from pathlib import Path

from common import (function_summary, latest_experiment, load_analysis,
                    main_guard, run_pytracer, scratch_with, write_csv)

WORKLOADS = Path(__file__).resolve().parent / "workloads"
SCRIPT = WORKLOADS / "sklearn_pipeline.py"
REPEAT = 10
PLUGINS = ["--plugins", "numpy", "sklearn"]


def run() -> int:
    workdir = scratch_with(SCRIPT)

    # float64 pipeline
    run_pytracer(["run", SCRIPT.name, "--repeat", str(REPEAT), *PLUGINS,
                  "--store-arrays", "always"], cwd=workdir)
    exp64 = latest_experiment(workdir)

    # identical pipeline in float32 (the "upgrade" under test in the A/B)
    run_pytracer(["run", SCRIPT.name, "--repeat", str(REPEAT), *PLUGINS,
                  "--store-arrays", "always", "--", "--float32"], cwd=workdir)
    exp32 = latest_experiment(workdir)

    rows = []
    funcs64, funcs32 = function_summary(exp64), function_summary(exp32)
    for fn, row in sorted(funcs64.items(),
                          key=lambda kv: kv[1]["min_output_sig_bits"] or 53.0):
        f32 = funcs32.get(fn, {})
        def fmt(value):
            return round(value, 2) if value is not None else ""

        rows.append({
            "function": fn,
            "min_sig_f64": fmt(row["min_output_sig_bits"]),
            "median_sig_f64": fmt(row["median_output_sig_bits"]),
            "min_sig_f32": fmt(f32.get("min_output_sig_bits")),
            "median_sig_f32": fmt(f32.get("median_output_sig_bits")),
            "amp_bits_f64": fmt(row["max_amplification_bits"]),
            "divergence": row["divergence_score"],
            "sig_basis": row["sig_basis"],
            "n_call_groups": row["n_call_groups"],
        })
    write_csv("e6_case.csv", rows)

    # CI gate: does the float64 pipeline clear a 20-bit threshold?
    check = run_pytracer(["check", str(exp64), "--min-sig-bits", "20",
                          "--max-divergence", "0.01"], cwd=workdir, check=False)
    # A/B: float32 vs float64
    diff = run_pytracer(["diff", str(exp64), str(exp32),
                         "--fail-on-regression"], cwd=workdir, check=False)

    meta = {
        "check_exit_code": check.returncode,
        "check_output": (check.stdout + check.stderr).strip(),
        "diff_exit_code": diff.returncode,
        "diff_output": (diff.stdout + diff.stderr).strip(),
        "alignment": load_analysis(exp64, "alignment"),
        "repeat": REPEAT,
    }
    out = Path(__file__).resolve().parent.parent / "results" / "e6_ci.json"
    out.write_text(json.dumps(meta, indent=1))
    print(f"wrote {out}")
    print(f"check exit={check.returncode}  diff exit={diff.returncode}")
    for line in meta["diff_output"].splitlines()[:12]:
        print("  " + line)
    return 0


if __name__ == "__main__":
    main_guard(run)
