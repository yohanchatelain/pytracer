"""E3 — Coverage honesty across tier combinations.

Run three workloads (numpy micro, scipy/numpy linear solve, sklearn
pipeline) under three instrumentation configurations and record what the
coverage report says each configuration observed and missed. Then close
the gap on one workload by adding the targets pytracer itself suggested.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from common import (EXAMPLES, function_summary, latest_experiment,
                    load_analysis, main_guard, run_pytracer, scratch_with,
                    write_csv)

WORKLOADS = Path(__file__).resolve().parent / "workloads"

CASES = [
    ("numpy micro", EXAMPLES / "simple_numpy.py", ["--plugins", "numpy"]),
    ("linear solve", EXAMPLES / "ill_conditioned_solve.py", ["--plugins", "numpy", "scipy"]),
    ("sklearn pipeline", WORKLOADS / "sklearn_pipeline.py",
     ["--plugins", "numpy", "sklearn"]),
]

CONFIGS = [
    ("patch", ["--instrument", "patch"]),
    ("hybrid", ["--instrument", "hybrid"]),
    ("hybrid+native", ["--instrument", "hybrid", "--native"]),
]


def coverage_row(exp: Path) -> dict:
    cov = load_analysis(exp, "coverage")
    untraced = cov["untraced_numerical_callables"]
    return {
        "events_per_tier": ";".join(
            f"{t}:{n}" for t, n in sorted(cov["calls_per_tier"].items())
        ),
        "traced_functions": len(cov["traced_functions"]),
        "untraced_callables": len(untraced),
        "untraced_calls": sum(u["calls"] for u in untraced),
        "native_kernels": len(cov["native_kernels"]),
        "native_kernel_calls": sum(
            entry["calls"] for entry in cov["native_kernels"].values()
        ),
    }


def run() -> int:
    rows = []
    for wname, script, plugins in CASES:
        for cname, flags in CONFIGS:
            workdir = scratch_with(script)
            run_pytracer(["run", script.name, "--repeat", "3", *plugins,
                          "--no-report", *flags], cwd=workdir)
            exp = latest_experiment(workdir)
            run_pytracer(["analyze", str(exp)], cwd=workdir)
            row = {"workload": wname, "config": cname, **coverage_row(exp)}
            rows.append(row)
            print(f"{wname:<18s} {cname:<14s} traced={row['traced_functions']:>3} "
                  f"untraced={row['untraced_callables']:>3} "
                  f"native={row['native_kernels']}")
            shutil.rmtree(workdir)

    # Closing the loop: rerun the sklearn pipeline with the exact targets
    # pytracer suggested from the monitor census.
    wname, script, plugins = CASES[2]
    workdir = scratch_with(script)
    run_pytracer(["run", script.name, "--repeat", "3", *plugins, "--no-report"],
                 cwd=workdir)
    run_pytracer(["analyze", str(latest_experiment(workdir))], cwd=workdir)
    cov = load_analysis(latest_experiment(workdir), "coverage")
    suggested = [u["function"] for u in cov["untraced_numerical_callables"]]
    target_flags = [arg for f in suggested for arg in ("--target", f)]
    run_pytracer(["run", script.name, "--repeat", "3", *plugins, "--no-report",
                  *target_flags], cwd=workdir)
    exp = latest_experiment(workdir)
    run_pytracer(["analyze", str(exp)], cwd=workdir)
    row = {"workload": wname, "config": "hybrid+suggested", **coverage_row(exp)}
    rows.append(row)
    print(f"{wname:<18s} {'hybrid+suggested':<14s} "
          f"traced={row['traced_functions']} untraced={row['untraced_callables']} "
          f"(added {len(suggested)} suggested targets)")
    shutil.rmtree(workdir)

    write_csv("e3_coverage.csv", rows)
    return 0


if __name__ == "__main__":
    main_guard(run)
