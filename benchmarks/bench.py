#!/usr/bin/env python
"""Pytracer overhead benchmarks.

Measures wall-time overhead ratio, event throughput, and trace size for each
instrumentation tier against an untraced baseline, in-process (subprocess
startup excluded so the numbers reflect steady-state tracing cost).

    python benchmarks/bench.py [--iterations N] [--markdown]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time

import numpy as np

from pytracer.instrumentation.patcher import Patcher, resolve_targets
from pytracer.instrumentation.recorder import Recorder, set_active_recorder
from pytracer.instrumentation.tracer_array import taint
from pytracer.trace.writer import TraceWriter


def workload_small_calls(n: int) -> float:
    """Many small traced calls: per-call overhead dominates."""
    x = np.arange(100.0)
    total = 0.0
    for _ in range(n):
        total += float(np.sum(x))
    return total


def workload_large_arrays(n: int) -> float:
    """Few calls on large arrays: summary cost dominates."""
    x = np.arange(2_000_000.0)
    total = 0.0
    for _ in range(max(1, n // 200)):
        total += float(np.sum(x))
    return total


def workload_operators(n: int) -> float:
    """Operator-heavy loop; only visible to taint mode."""
    x = np.arange(100.0)
    for _ in range(n):
        x = x * 1.0000001 + 0.0
    return float(x[0])


def timed(fn, *args) -> float:
    start = time.perf_counter()
    fn(*args)
    return time.perf_counter() - start


def run_mode(mode: str, workload, n: int) -> dict:
    if mode == "baseline":
        elapsed = timed(workload, n)
        return {"time": elapsed, "events": 0, "bytes": 0}

    with tempfile.TemporaryDirectory() as tmp:
        writer = TraceWriter(tmp)
        recorder = Recorder(writer, "bench", capture_backtrace=True)
        set_active_recorder(recorder)
        patcher = Patcher(recorder)
        try:
            if mode == "t1":
                patcher.patch(resolve_targets(["numpy.sum"]).resolved)
                elapsed = timed(workload, n)
            elif mode == "t2":
                patcher.patch(resolve_targets(["numpy.add", "numpy.multiply"]).resolved)
                elapsed = timed(workload, n)
            elif mode == "taint":
                def tainted(k, _w=workload):
                    # taint the workload's array space by running on tainted input
                    x = taint(np.arange(100.0))
                    for _ in range(k):
                        x = x * 1.0000001 + 0.0
                    return float(x.view(np.ndarray)[0])

                elapsed = timed(tainted, n)
            else:
                raise ValueError(mode)
        finally:
            patcher.unpatch()
            set_active_recorder(None)
            writer.close()
        size = writer.path.stat().st_size if writer.path.exists() else 0
        return {"time": elapsed, "events": writer.n_events, "bytes": size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    n = args.iterations

    cases = [
        ("small calls (numpy.sum x N)", workload_small_calls, ["baseline", "t1"]),
        ("large arrays (2e6 elements)", workload_large_arrays, ["baseline", "t1"]),
        ("operator loop (x*a+b x N)", workload_operators, ["baseline", "taint"]),
    ]

    rows = []
    for name, workload, modes in cases:
        base = run_mode("baseline", workload, n)
        for mode in modes:
            r = base if mode == "baseline" else run_mode(mode, workload, n)
            rows.append({
                "workload": name,
                "mode": mode,
                "time_s": r["time"],
                "ratio": r["time"] / base["time"] if base["time"] else float("nan"),
                "events": r["events"],
                "events_per_s": r["events"] / r["time"] if r["time"] else 0,
                "bytes_per_event": (r["bytes"] / r["events"]) if r["events"] else 0,
            })

    if args.markdown:
        print("| Workload | Mode | Time (s) | Overhead | Events | Events/s | B/event |")
        print("|---|---|---|---|---|---|---|")
        for r in rows:
            print(
                f"| {r['workload']} | {r['mode']} | {r['time_s']:.3f} "
                f"| {r['ratio']:.2f}x | {r['events']} "
                f"| {r['events_per_s']:,.0f} | {r['bytes_per_event']:.0f} |"
            )
    else:
        for r in rows:
            print(
                f"{r['workload']:<32s} {r['mode']:<9s} {r['time_s']:8.3f}s "
                f"{r['ratio']:6.2f}x  {r['events']:>8d} ev "
                f"{r['events_per_s']:>12,.0f} ev/s {r['bytes_per_event']:6.0f} B/ev"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
