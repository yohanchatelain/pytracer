"""E4 — Alignment robustness under control-flow divergence.

Two workloads whose traced call sequences differ across runs (a random
branch and a random-length loop), aligned with each of the three
strategies. Reports how many call groups each strategy matches and how
many it must declare divergent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from common import (PROGRAMS, latest_experiment, load_analysis, main_guard,
                    run_pytracer, scratch_with, write_csv)

WORKLOADS = Path(__file__).resolve().parent / "workloads"

CASES = [
    ("random branch", PROGRAMS / "control_flow_divergence.py"),
    ("random-length loop", WORKLOADS / "random_loop_divergence.py"),
]

STRATEGIES = ["strict", "callsite", "fuzzy"]
REPEAT = 20


def run() -> int:
    rows = []
    for wname, script in CASES:
        # One trace per workload; realign it under each strategy so the
        # strategies see the identical set of runs.
        workdir = scratch_with(script)
        run_pytracer(["run", script.name, "--repeat", str(REPEAT),
                      "--plugins", "numpy", "--no-report"], cwd=workdir)
        exp = latest_experiment(workdir)
        for strategy in STRATEGIES:
            proc = run_pytracer(["analyze", str(exp), "--alignment", strategy],
                                cwd=workdir, check=False)
            if proc.returncode != 0:
                # strict alignment refuses divergent traces outright:
                # the abort is the datapoint.
                rows.append({
                    "workload": wname, "strategy": strategy, "runs": REPEAT,
                    "total_call_groups": "", "matched_call_groups": 0,
                    "divergent_call_groups": "", "matched_fraction": 0.0,
                    "truncated_runs": "", "outcome": "aborts",
                })
                print(f"{wname:<20s} {strategy:<9s} ABORTS: "
                      f"{proc.stderr.strip().splitlines()[-1][:80]}")
                continue
            al = load_analysis(exp, "alignment")
            total = al["total_call_groups"]
            matched = al["matched_call_groups"]
            rows.append({
                "workload": wname,
                "strategy": strategy,
                "runs": al["runs"],
                "total_call_groups": total,
                "matched_call_groups": matched,
                "divergent_call_groups": al["divergent_call_groups"],
                "matched_fraction": round(matched / total, 3) if total else "",
                "truncated_runs": len(al["truncated_runs"]),
                "outcome": "ok",
            })
            print(f"{wname:<20s} {strategy:<9s} matched {matched}/{total}")
        shutil.rmtree(workdir)

    write_csv("e4_alignment.csv", rows)
    return 0


if __name__ == "__main__":
    main_guard(run)
