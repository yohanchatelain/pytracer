"""Dashboard data layer.

Loads a completed experiment once at startup: the precomputed ``analysis/``
aggregates (never recomputed) plus the raw per-call records, re-aligned
in memory so the dashboard can offer call-level drill-down that the JSON
summaries do not carry. Array payloads and event timelines are loaded
lazily and cached.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from pytracer._errors import AlignmentError
from pytracer.analysis.aggregate import SIG_CAP_BITS, sig_bits
from pytracer.analysis.align import align, load_experiment_calls
from pytracer.report.model import build_report_data
from pytracer.storage.arrays import load_array
from pytracer.trace.reader import CallRecord
from pytracer.trace.writer import EVENTS_FILENAME

MAX_TIMELINE_POINTS_WEBGL = 5_000
MAX_GANTT_SPANS = 400


def elementwise_sig_array(stack: np.ndarray) -> np.ndarray:
    """Per-element significant bits for a (n_runs, *shape) stack.

    Same estimator as analysis.elementwise, but returns the full per-element
    array (NaN where undefined) instead of summary quantiles.
    """
    runs = np.atleast_2d(stack.reshape(stack.shape[0], -1)).astype(np.float64, copy=False)
    with np.errstate(all="ignore"):
        mean = runs.mean(axis=0)
        std = runs.std(axis=0)
        sig = np.full(mean.shape, np.nan)
        finite = np.isfinite(mean) & np.isfinite(std)
        sig[finite & (std == 0.0)] = SIG_CAP_BITS
        sig[finite & (std > 0.0) & (mean == 0.0)] = 0.0
        measurable = finite & (std > 0.0) & (mean != 0.0)
        sig[measurable] = np.clip(
            -np.log2(std[measurable] / np.abs(mean[measurable])), 0.0, SIG_CAP_BITS
        )
    return sig.reshape(stack.shape[1:])


def as_matrix(values: np.ndarray) -> np.ndarray:
    """Squash an array to 2-D for heatmap display."""
    arr = np.asarray(values)
    if arr.ndim == 0:
        return arr.reshape(1, 1)
    if arr.ndim == 1:
        return arr.reshape(1, -1)
    if arr.ndim == 2:
        return arr
    return arr.reshape(arr.shape[0], -1)


class ExperimentData:
    """All data the dashboard serves, keyed for callback lookups."""

    def __init__(self, experiment_dir: str | Path):
        self.experiment_dir = Path(experiment_dir)
        self.report = build_report_data(self.experiment_dir)

        run_ids, calls_per_run, truncated = load_experiment_calls(self.experiment_dir)
        self.run_ids: list[str] = run_ids
        self.run_dirs = [self.experiment_dir / "runs" / run_id for run_id in run_ids]
        mode = self.report.get("alignment", {}).get("alignment_mode", "callsite")
        try:
            self.alignment = align(run_ids, calls_per_run, mode=mode,
                                   truncated_runs=truncated)
        except AlignmentError:
            # strict mode re-raises on divergence; the dashboard still wants
            # to show whatever aligned.
            self.alignment = align(run_ids, calls_per_run, mode="callsite",
                                   truncated_runs=truncated)

        self.functions: list[str] = [r["function"] for r in self.report.get("functions", [])]
        self.timeline_rows: list[dict] = self._build_timeline_rows()
        self._element_cache: dict[tuple[int, str, str], tuple | None] = {}
        self._source_cache: dict[tuple[str | None, int | None], dict | None] = {}
        self._spans_cache: dict[str, tuple[list[dict], int]] = {}

    # ---------------------------------------------------------------- timeline

    def _build_timeline_rows(self) -> list[dict]:
        """One row per (aligned call group, argument, phase).

        ``x`` is the per-function invocation index in program order, the
        cross-run equivalent of pytracer 1's per-call timeline axis.
        """
        rows: list[dict] = []
        counters: dict[str, int] = {}
        for gidx, group in enumerate(self.alignment.groups):
            function = group.function
            x = counters.get(function, 0)
            counters[function] = x + 1
            calls = [c for c in group.calls if c is not None]
            file, lineno = group.key[3], group.key[4]
            exception = next((c.exception for c in calls if c.exception), None)
            tier = calls[0].tier if calls else ""
            for phase, getter, refs_getter in (
                ("input", lambda c: c.inputs, lambda c: c.input_refs),
                ("output", lambda c: c.outputs, lambda c: c.output_refs),
            ):
                arg_names: set[str] = set()
                for c in calls:
                    arg_names.update(getter(c))
                for arg in sorted(arg_names):
                    summaries = [getter(c).get(arg) for c in calls]
                    present = [s for s in summaries if s is not None]
                    if not present:
                        continue
                    means = [s.mean for s in present]
                    clean = [m for m in means if m is not None and math.isfinite(m)]
                    mean = sum(clean) / len(clean) if clean else None
                    if clean and len(clean) > 1:
                        mu = mean
                        std = math.sqrt(sum((m - mu) ** 2 for m in clean) / len(clean))
                    else:
                        std = None
                    mins = [s.min for s in present if s.min is not None]
                    maxs = [s.max for s in present if s.max is not None]
                    has_arrays = group.complete and all(
                        refs_getter(c).get(arg) for c in calls
                    )
                    rows.append({
                        "gidx": gidx,
                        "function": function,
                        "arg": arg,
                        "phase": phase,
                        "x": x,
                        "file": file,
                        "lineno": lineno,
                        "tier": tier,
                        "dtype": present[0].dtype,
                        "shape": "x".join(map(str, present[0].shape)) or "scalar",
                        "size": present[0].size,
                        "n_runs_present": len(present),
                        "sig_proxy": sig_bits(means),
                        "mean": mean,
                        "std": std,
                        "min": min(mins) if mins else None,
                        "max": max(maxs) if maxs else None,
                        "nan_count": sum(s.nan_count for s in present),
                        "inf_count": sum(s.inf_count for s in present),
                        "nan_var": len({s.nan_count for s in present}) > 1,
                        "inf_var": len({s.inf_count for s in present}) > 1,
                        "divergent": not group.complete,
                        "has_arrays": has_arrays,
                        "exception": exception,
                    })
        return rows

    def timeline_for(self, functions: list[str], phases: list[str]) -> list[dict]:
        wanted = set(functions)
        phase_set = set(phases)
        return [
            r for r in self.timeline_rows
            if r["function"] in wanted and r["phase"] in phase_set
        ]

    def element_sig_min(self, gidx: int, phase: str, arg: str) -> float | None:
        loaded = self.element_stack(gidx, phase, arg)
        if loaded is None:
            return None
        sig = loaded[0]
        finite = sig[np.isfinite(sig)]
        return float(finite.min()) if finite.size else None

    # ------------------------------------------------------------- drill-down

    def group_calls(self, gidx: int) -> list[CallRecord | None]:
        return self.alignment.groups[gidx].calls

    def group_detail(self, gidx: int, phase: str, arg: str) -> list[dict]:
        """Per-run summary statistics for one argument of one aligned call."""
        rows = []
        for run_id, call in zip(self.run_ids, self.group_calls(gidx), strict=True):
            if call is None:
                rows.append({"run": run_id, "status": "missing (divergent)"})
                continue
            summary = (call.inputs if phase == "input" else call.outputs).get(arg)
            if summary is None:
                rows.append({"run": run_id, "status": "argument absent"})
                continue
            rows.append({
                "run": run_id,
                "status": "exception" if call.exception else "ok",
                "dtype": summary.dtype,
                "shape": "x".join(map(str, summary.shape)) or "scalar",
                "mean": summary.mean,
                "std": summary.std,
                "min": summary.min,
                "max": summary.max,
                "l2_norm": summary.l2_norm,
                "linf_norm": summary.linf_norm,
                "nan": summary.nan_count,
                "inf": summary.inf_count,
                "zero": summary.zero_count,
                "subnormal": summary.subnormal_count,
                "fingerprint": (summary.fingerprint or "")[:12],
            })
        return rows

    def element_stack(self, gidx: int, phase: str, arg: str):
        """(sig_array, stack) from stored per-run arrays, or None."""
        key = (gidx, phase, arg)
        if key in self._element_cache:
            return self._element_cache[key]
        result = None
        calls = self.group_calls(gidx)
        if all(c is not None for c in calls):
            refs = [
                (c.input_refs if phase == "input" else c.output_refs).get(arg)
                for c in calls
            ]
            if all(refs):
                arrays = [
                    load_array(d, r)
                    for d, r in zip(self.run_dirs, refs, strict=True)
                ]
                shapes = {a.shape for a in arrays if a is not None}
                if not any(a is None for a in arrays) and len(shapes) == 1:
                    stack = np.stack([
                        np.abs(a) if a.dtype.kind == "c" else a for a in arrays
                    ]).astype(np.float64, copy=False)
                    result = (elementwise_sig_array(stack), stack)
        self._element_cache[key] = result
        return result

    # ----------------------------------------------------------------- source

    def source_context(self, file: str | None, lineno: int | None,
                       radius: int = 7) -> dict | None:
        """Source lines around a callsite, if the file is still readable."""
        if not file or not lineno:
            return None
        if (key := (file, lineno)) in self._source_cache:
            return self._source_cache[key]
        path = Path(file)
        if not path.is_file():
            return None
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            return None
        start = max(1, lineno - radius)
        end = min(len(lines), lineno + radius)
        context = {
            "file": file,
            "lineno": lineno,
            "start": start,
            "lines": lines[start - 1:end],
        }
        self._source_cache[key] = context
        return context

    # ------------------------------------------------------------------ spans

    def run_spans(self, run_id: str) -> tuple[list[dict], int]:
        """Call spans (name, tier, start_us, dur_us, depth) for one run.

        Returns (spans, total) where spans is capped at MAX_GANTT_SPANS
        longest-duration calls and total is the uncapped count.
        """
        if run_id in self._spans_cache:
            return self._spans_cache[run_id]

        from pytracer.trace.reader import iter_events

        run_dir = self.experiment_dir / "runs" / run_id
        events_path = run_dir / EVENTS_FILENAME
        if not events_path.is_file():
            return [], 0
        events, _ = iter_events(events_path)
        spans: dict[int, dict] = {}
        parents: dict[int, int | None] = {}
        for ev in events:
            if ev.ts_ns is None:
                continue
            span = spans.setdefault(ev.call_id, {
                "name": f"{ev.module}.{ev.qualname}"
                + (f".{ev.ufunc_method}"
                   if ev.ufunc_method not in (None, "__call__") else ""),
                "tier": ev.tier,
                "start": ev.ts_ns,
                "end": ev.ts_ns,
                "exception": None,
            })
            parents.setdefault(ev.call_id, ev.parent_call_id)
            span["start"] = min(span["start"], ev.ts_ns)
            span["end"] = max(span["end"], ev.ts_ns)
            if ev.phase == "exception":
                span["exception"] = ev.note or "exception"
        if not spans:
            return [], 0

        def depth(call_id: int) -> int:
            d, cursor, seen = 0, parents.get(call_id), set()
            while cursor is not None and cursor in parents and cursor not in seen:
                seen.add(cursor)
                d += 1
                cursor = parents.get(cursor)
            return d

        t0 = min(s["start"] for s in spans.values())
        out = []
        for call_id, s in spans.items():
            out.append({
                "name": s["name"],
                "tier": s["tier"],
                "start_us": (s["start"] - t0) / 1_000,
                "dur_us": max((s["end"] - s["start"]) / 1_000, 0.001),
                "depth": depth(call_id),
                "exception": s["exception"],
            })
        total = len(out)
        out.sort(key=lambda s: -s["dur_us"])
        out = out[:MAX_GANTT_SPANS]
        out.sort(key=lambda s: s["start_us"])
        self._spans_cache[run_id] = (out, total)
        return out, total
