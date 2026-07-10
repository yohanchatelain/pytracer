#!/usr/bin/env python
"""Pytracer overhead benchmarks.

Measures repeated-median wall-time overhead, event throughput, artifact size,
and file count for each instrumentation tier against an untraced baseline,
in-process (subprocess startup excluded so the numbers reflect steady-state
capture cost). Summary, metadata-only, hybrid, and default array-storage modes
are reported separately.

    python benchmarks/bench.py [--iterations N] [--repeats N] [--markdown]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from pytracer.instrumentation.monitor import Monitor
from pytracer.instrumentation.patcher import Patcher, resolve_targets
from pytracer.instrumentation.recorder import Recorder, set_active_recorder
from pytracer.instrumentation.tracer_array import taint
from pytracer.storage.arrays import ArrayStore
from pytracer.trace.summary import summarize_value
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


def workload_direct_ufunc(n: int) -> float:
    """Direct module-attribute ufunc calls; visible to T2."""
    x = np.arange(100.0)
    for _ in range(n):
        x = np.add(x, 1.0)
    return float(x[0])


def workload_small_calls_storage(n: int) -> float:
    """Bound the default-storage case so it cannot create 20k files per sample."""
    return workload_small_calls(min(n, 1_000))


def timed(fn, *args) -> float:
    start = time.perf_counter()
    fn(*args)
    return time.perf_counter() - start


def run_mode(mode: str, workload, n: int) -> dict:
    if mode == "baseline":
        elapsed = timed(workload, n)
        return {"time": elapsed, "events": 0, "bytes": 0, "files": 0}

    with tempfile.TemporaryDirectory() as tmp:
        writer = TraceWriter(tmp)
        metadata = mode.endswith("metadata")
        default_storage = mode == "hybrid-default"
        array_store = (
            ArrayStore(tmp, mode="auto", threshold=100_000, backend="npy")
            if default_storage
            else None
        )
        recorder = Recorder(
            writer,
            "bench",
            capture_backtrace=True,
            mode="metadata" if metadata else "summary",
            array_store=array_store,
        )
        set_active_recorder(recorder)
        patcher = Patcher(recorder)
        monitor = None
        try:
            if mode.startswith("t1") or mode.startswith("hybrid"):
                patcher.patch(resolve_targets(["numpy.sum"]).resolved)
                if mode.startswith("hybrid"):
                    monitor = Monitor(scope_dir=Path(__file__).parent, run_dir=tmp)
                    monitor.start()
                elapsed = timed(workload, n)
            elif mode.startswith("t2"):
                patcher.patch(resolve_targets(["numpy.add", "numpy.multiply"]).resolved)
                elapsed = timed(workload, n)
            elif mode.startswith("taint"):
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
            if monitor is not None:
                monitor.stop()
            set_active_recorder(None)
            writer.close()
        paths = [path for path in Path(tmp).rglob("*") if path.is_file()]
        size = sum(path.stat().st_size for path in paths)
        return {
            "time": elapsed,
            "events": writer.n_events,
            "bytes": size,
            "files": len(paths),
        }


def measure_mode(mode: str, workload, n: int, repeats: int) -> dict:
    samples = [run_mode(mode, workload, n) for _ in range(repeats)]
    return {
        "time": statistics.median(sample["time"] for sample in samples),
        "events": int(statistics.median(sample["events"] for sample in samples)),
        "bytes": int(statistics.median(sample["bytes"] for sample in samples)),
        "files": int(statistics.median(sample["files"] for sample in samples)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    n = args.iterations

    cases = [
        (
            "small calls (numpy.sum x N)",
            workload_small_calls,
            ["baseline", "t1-summary", "t1-metadata", "hybrid-summary", "hybrid-metadata"],
        ),
        (
            "default capture + array store",
            workload_small_calls_storage,
            ["baseline", "hybrid-default"],
        ),
        (
            "large arrays (2e6 elements)",
            workload_large_arrays,
            ["baseline", "t1-summary", "t1-metadata"],
        ),
        (
            "direct np.add x N",
            workload_direct_ufunc,
            ["baseline", "t2-summary", "t2-metadata"],
        ),
        (
            "operator loop (x*a+b x N)",
            workload_operators,
            ["baseline", "taint-summary", "taint-metadata"],
        ),
    ]

    # Initialize NumPy reduction/norm dispatch and fault in representative
    # data before collecting samples. The median then rejects scheduler noise
    # rather than measuring one-time library startup.
    warm = np.arange(2_000_000.0)
    summarize_value(warm)
    summarize_value(np.float64(1.0))
    for _, workload, _ in cases:
        workload(min(n, 200))

    rows = []
    for name, workload, modes in cases:
        base = measure_mode("baseline", workload, n, args.repeats)
        for mode in modes:
            r = base if mode == "baseline" else measure_mode(
                mode, workload, n, args.repeats
            )
            rows.append({
                "workload": name,
                "mode": mode,
                "time_s": r["time"],
                "ratio": r["time"] / base["time"] if base["time"] else float("nan"),
                "events": r["events"],
                "events_per_s": r["events"] / r["time"] if r["time"] else 0,
                "bytes_per_event": (r["bytes"] / r["events"]) if r["events"] else 0,
                "files": r["files"],
            })

    if args.markdown:
        print("| Workload | Mode | Time (s) | Overhead | Events | Events/s | B/event | Files |")
        print("|---|---|---|---|---|---|---|---|")
        for r in rows:
            print(
                f"| {r['workload']} | {r['mode']} | {r['time_s']:.3f} "
                f"| {r['ratio']:.2f}x | {r['events']} "
                f"| {r['events_per_s']:,.0f} | {r['bytes_per_event']:.0f} "
                f"| {r['files']} |"
            )
    else:
        for r in rows:
            print(
                f"{r['workload']:<32s} {r['mode']:<9s} {r['time_s']:8.3f}s "
                f"{r['ratio']:6.2f}x  {r['events']:>8d} ev "
                f"{r['events_per_s']:>12,.0f} ev/s {r['bytes_per_event']:6.0f} B/ev "
                f"{r['files']:>6d} files"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
