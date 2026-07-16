"""E2 — Per-tier tracing overhead.

In-process microbenchmarks (reusing benchmarks/bench.py machinery) for
T1 boundary patching, T2 ufunc proxy, and T3 taint, plus an end-to-end
wall-clock comparison for the T4 monitor tier. Each measurement is
repeated REPEAT times; the median is reported.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

from common import PROGRAMS, REPO, VENV_PY, main_guard, scratch_with, write_csv

REPEAT = 5
ITER_DEFAULT = 20_000
ITER_TAINT = 5_000

WORKER = r"""
import json, sys
sys.path.insert(0, {bench_dir!r})
from bench import run_mode, workload_small_calls, workload_large_arrays, workload_operators

mode, workload_name, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
workload = {{"small": workload_small_calls,
             "large": workload_large_arrays,
             "operators": workload_operators}}[workload_name]
print(json.dumps(run_mode(mode, workload, n)))
"""


def bench_once(mode: str, workload: str, n: int) -> dict:
    proc = subprocess.run(
        [str(VENV_PY), "-c", WORKER.format(bench_dir=str(REPO / "benchmarks")),
         mode, workload, str(n)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def bench_median(mode: str, workload: str, n: int) -> dict:
    runs = [bench_once(mode, workload, n) for _ in range(REPEAT)]
    times = [r["time"] for r in runs]
    mid = runs[times.index(statistics.median_low(times))]
    return {"time": statistics.median(times), "events": mid["events"],
            "bytes": mid["bytes"], "spread": max(times) - min(times)}


def monitor_end_to_end() -> tuple[float, float]:
    """Wall-clock of `pytracer run --instrument monitor` vs plain python."""
    script = PROGRAMS / "simple_numpy.py"
    workdir = scratch_with(script)

    def timed(cmd: list[str]) -> float:
        start = time.perf_counter()
        subprocess.run(cmd, cwd=workdir, capture_output=True, check=True)
        return time.perf_counter() - start

    base = statistics.median(
        timed([str(VENV_PY), script.name]) for _ in range(REPEAT)
    )
    traced = statistics.median(
        timed([str(VENV_PY), "-m", "pytracer.cli.main", "run", script.name,
               "--instrument", "monitor", "--no-report"])
        for _ in range(REPEAT)
    )
    return base, traced


CASES = [
    # label, tier, mode, workload, iterations
    ("20k tiny numpy.sum calls", "T1", "t1", "small", ITER_DEFAULT),
    ("2M-element numpy.sum calls", "T1", "t1", "large", ITER_DEFAULT),
    ("20k tiny numpy.sum calls", "T2", "t2", "small", ITER_DEFAULT),
    ("operator loop (x*a+b)", "T3", "taint", "operators", ITER_TAINT),
]


def run() -> int:
    rows = []
    for label, tier, mode, workload, n in CASES:
        base = bench_median("baseline", workload, n)
        res = bench_median(mode, workload, n)
        ratio = res["time"] / base["time"]
        rows.append({
            "workload": label, "tier": tier, "iterations": n,
            "baseline_s": round(base["time"], 4),
            "traced_s": round(res["time"], 4),
            "overhead_x": round(ratio, 1),
            "events": res["events"],
            "events_per_s": round(res["events"] / res["time"]) if res["time"] else 0,
            "bytes_per_event": round(res["bytes"] / res["events"]) if res["events"] else 0,
            "spread_s": round(res["spread"], 4),
        })
        print(f"{label:<28s} {tier}: {ratio:6.1f}x")

    base, traced = monitor_end_to_end()
    rows.append({
        "workload": "end-to-end simple_numpy.py", "tier": "T4", "iterations": 1,
        "baseline_s": round(base, 4), "traced_s": round(traced, 4),
        "overhead_x": round(traced / base, 1),
        "events": "", "events_per_s": "", "bytes_per_event": "",
        "spread_s": "",
    })
    print(f"{'end-to-end monitor':<28s} T4: {traced / base:6.1f}x")

    write_csv("e2_overhead.csv", rows)
    return 0


if __name__ == "__main__":
    main_guard(run)
