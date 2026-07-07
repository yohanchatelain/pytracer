"""Export an experiment as a Perfetto / Chrome Trace Event Format timeline.

Each run becomes a process row (pid = run index); each traced call becomes a
complete event ("X") spanning its input→output timestamps, annotated with
the call's summary statistics. Open the file at https://ui.perfetto.dev or
chrome://tracing.
"""

from __future__ import annotations

import json
from pathlib import Path

from pytracer._errors import PytracerError
from pytracer.trace.event import TraceEvent
from pytracer.trace.reader import iter_events
from pytracer.trace.writer import EVENTS_FILENAME


def _call_spans(events: list[TraceEvent]) -> list[dict]:
    spans: dict[int, dict] = {}
    for ev in events:
        if ev.ts_ns is None:
            continue
        span = spans.setdefault(
            ev.call_id,
            {
                "name": f"{ev.module}.{ev.qualname}"
                + (f".{ev.ufunc_method}" if ev.ufunc_method not in (None, "__call__") else ""),
                "tier": ev.tier,
                "start": ev.ts_ns,
                "end": ev.ts_ns,
                "args": {},
                "exception": None,
            },
        )
        span["start"] = min(span["start"], ev.ts_ns)
        span["end"] = max(span["end"], ev.ts_ns)
        if ev.phase == "exception":
            span["exception"] = ev.note
        elif ev.summary is not None and ev.arg_name:
            span["args"][f"{ev.phase}:{ev.arg_name}"] = {
                "dtype": ev.summary.dtype,
                "shape": list(ev.summary.shape),
                "mean": ev.summary.mean,
                "std": ev.summary.std,
            }
    return list(spans.values())


def export_perfetto(experiment_dir: str | Path, output: str | Path | None = None) -> Path:
    experiment_dir = Path(experiment_dir)
    runs_dir = experiment_dir / "runs"
    if not runs_dir.is_dir():
        raise PytracerError(f"{experiment_dir}: no runs directory")

    trace_events: list[dict] = []
    run_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    if not run_dirs:
        raise PytracerError(f"{experiment_dir}: no runs found")

    for pid, run_dir in enumerate(run_dirs):
        events_path = run_dir / EVENTS_FILENAME
        if not events_path.is_file():
            continue
        events, _truncated = iter_events(events_path)
        spans = _call_spans(events)
        if not spans:
            continue
        base = min(s["start"] for s in spans)
        trace_events.append(
            {"ph": "M", "pid": pid, "name": "process_name",
             "args": {"name": run_dir.name}}
        )
        for span in spans:
            entry = {
                "name": span["name"],
                "cat": span["tier"],
                "ph": "X",
                "pid": pid,
                "tid": 0,
                "ts": (span["start"] - base) / 1000.0,  # microseconds
                "dur": max((span["end"] - span["start"]) / 1000.0, 0.001),
                "args": span["args"],
            }
            if span["exception"]:
                entry["args"]["exception"] = span["exception"]
            trace_events.append(entry)

    if not trace_events:
        raise PytracerError(
            f"{experiment_dir}: no timestamped events "
            f"(traces predate the ts_ns field?)"
        )

    out = Path(output) if output else experiment_dir / "report" / "trace.perfetto.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"traceEvents": trace_events, "displayTimeUnit": "ms"}))
    return out
