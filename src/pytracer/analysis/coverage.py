"""Coverage accounting: what was observed, at which tier, and what was not.

Absence of an instability signal must never be read as evidence of
stability. This module merges the T4 monitor's C-call census with the set
of traced targets to report untraced numerical callables — which doubles as
the `suggest-targets` list.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pytracer.instrumentation.monitor import MONITOR_FILENAME
from pytracer.instrumentation.native import NATIVE_LOG_FILENAME, parse_native_log
from pytracer.trace.reader import CallRecord

_SUGGESTION_MODULE_PREFIXES = ("numpy", "scipy", "sklearn", "pandas", "torch", "jax")


def build_coverage(
    experiment_dir: str | Path,
    calls_per_run: list[list[CallRecord]],
    target_specs: list[str],
) -> dict:
    events_per_tier: Counter[str] = Counter()
    traced_functions: set[str] = set()
    for calls in calls_per_run:
        for call in calls:
            events_per_tier[call.tier] += 1
            traced_functions.add(f"{call.module}.{call.qualname}")

    c_calls: Counter[str] = Counter()
    monitor_available = False
    runs_dir = Path(experiment_dir) / "runs"
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            monitor_path = run_dir / MONITOR_FILENAME
            if not monitor_path.is_file():
                continue
            data = json.loads(monitor_path.read_text())
            monitor_available = monitor_available or data.get("available", False)
            for name, count in data.get("c_calls", {}).items():
                c_calls[name] += count

    native_kernels: dict[str, dict] = {}
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            for name, entry in parse_native_log(run_dir / NATIVE_LOG_FILENAME).items():
                agg = native_kernels.setdefault(name, {"calls": 0, "volume": 0})
                agg["calls"] += entry["calls"]
                agg["volume"] += entry["volume"]

    untraced = [
        {"function": name, "calls": count}
        for name, count in c_calls.most_common()
        if name not in traced_functions
        and name.startswith(_SUGGESTION_MODULE_PREFIXES)
        and not name.startswith("numpy._")
    ]

    return {
        "calls_per_tier": dict(events_per_tier),
        "native_kernels": native_kernels,
        "traced_functions": sorted(traced_functions),
        "targets_configured": target_specs,
        "monitor_available": monitor_available,
        "untraced_numerical_callables": untraced[:50],
        "notes": [
            "Operator dispatch on ndarrays (a + b) is not observable at tiers t1/t2.",
            "Calls made inside compiled extensions (C/Cython) are not observable "
            "at any Python tier.",
        ]
        + ([] if monitor_available else ["sys.monitoring unavailable: C-call census empty."]),
    }


def write_coverage(experiment_dir: str | Path, coverage: dict) -> Path:
    analysis_dir = Path(experiment_dir) / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    path = analysis_dir / "coverage.json"
    path.write_text(json.dumps(coverage, indent=2))
    return path
