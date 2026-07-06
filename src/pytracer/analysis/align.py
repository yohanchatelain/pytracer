"""Align calls across repeated runs.

The unit of alignment is the *call* (input+output events sharing a call_id),
matched across runs by callsite key: (module, qualname, ufunc_method,
source file, source line, occurrence). Occurrence is a deterministic
per-callsite counter, so identical control flow aligns exactly.

Modes:
- strict:   every call must match in every run; first divergence is an error.
- callsite: keys missing from some runs are reported, matched keys proceed.
- fuzzy:    alias of callsite in this version (LCS matching planned); it
            exists so configs written now keep working when it lands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pytracer._errors import AlignmentError, PytracerError
from pytracer.trace.reader import CallKey, CallRecord, load_run_calls


@dataclass(slots=True)
class AlignedGroup:
    key: CallKey
    calls: list[CallRecord | None]  # one slot per run

    @property
    def complete(self) -> bool:
        return all(c is not None for c in self.calls)

    @property
    def function(self) -> str:
        for c in self.calls:
            if c is not None:
                return c.function
        raise ValueError("empty aligned group")


@dataclass(slots=True)
class Alignment:
    mode: str
    run_ids: list[str]
    groups: list[AlignedGroup] = field(default_factory=list)
    truncated_runs: list[str] = field(default_factory=list)

    @property
    def matched(self) -> list[AlignedGroup]:
        return [g for g in self.groups if g.complete]

    @property
    def divergent(self) -> list[AlignedGroup]:
        return [g for g in self.groups if not g.complete]

    def summary_dict(self) -> dict:
        per_function: dict[str, dict] = {}
        for group in self.groups:
            entry = per_function.setdefault(
                group.function, {"expected": 0, "missing": 0, "missing_in_runs": set()}
            )
            entry["expected"] += 1
            if not group.complete:
                entry["missing"] += 1
                for run_id, call in zip(self.run_ids, group.calls, strict=True):
                    if call is None:
                        entry["missing_in_runs"].add(run_id)
        divergent_calls = [
            {
                "function": fn,
                "divergence_score": e["missing"] / e["expected"],
                "missing_in_runs": sorted(e["missing_in_runs"]),
            }
            for fn, e in sorted(per_function.items())
            if e["missing"]
        ]
        return {
            "alignment_mode": self.mode,
            "runs": len(self.run_ids),
            "run_ids": self.run_ids,
            "total_call_groups": len(self.groups),
            "matched_call_groups": len(self.matched),
            "divergent_call_groups": len(self.divergent),
            "truncated_runs": self.truncated_runs,
            "divergent_calls": divergent_calls,
        }


def load_experiment_calls(
    experiment_dir: str | Path,
) -> tuple[list[str], list[list[CallRecord]], list[str]]:
    runs_dir = Path(experiment_dir) / "runs"
    run_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []
    if not run_dirs:
        raise PytracerError(f"{experiment_dir}: no runs found")
    run_ids, calls_per_run, truncated = [], [], []
    for run_dir in run_dirs:
        calls, was_truncated = load_run_calls(run_dir)
        run_ids.append(run_dir.name)
        calls_per_run.append(calls)
        if was_truncated:
            truncated.append(run_dir.name)
    return run_ids, calls_per_run, truncated


def align(
    run_ids: list[str],
    calls_per_run: list[list[CallRecord]],
    mode: str = "callsite",
    truncated_runs: list[str] | None = None,
) -> Alignment:
    if mode == "fuzzy":
        mode = "callsite"  # LCS matching planned; callsite is the safe superset
    indexes = [{c.key: c for c in run_calls} for run_calls in calls_per_run]
    ordered_keys: list[CallKey] = []
    seen: set[CallKey] = set()
    for calls in calls_per_run:
        for call in calls:
            if call.key not in seen:
                seen.add(call.key)
                ordered_keys.append(call.key)

    alignment = Alignment(
        mode=mode, run_ids=run_ids, truncated_runs=list(truncated_runs or [])
    )
    for key in ordered_keys:
        group = AlignedGroup(key=key, calls=[idx.get(key) for idx in indexes])
        if mode == "strict" and not group.complete:
            missing = [
                run_ids[i] for i, call in enumerate(group.calls) if call is None
            ]
            raise AlignmentError(
                f"strict alignment failed: call {group.function} "
                f"(source {key[3]}:{key[4]}, occurrence {key[5]}) "
                f"missing in runs {missing}"
            )
        alignment.groups.append(group)
    return alignment


def write_alignment(experiment_dir: str | Path, alignment: Alignment) -> Path:
    analysis_dir = Path(experiment_dir) / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    path = analysis_dir / "alignment.json"
    path.write_text(json.dumps(alignment.summary_dict(), indent=2))
    return path
