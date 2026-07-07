"""Read captured events and reassemble them into calls.

A truncated final line (crashed run) is tolerated and reported; corruption
anywhere else raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import msgspec

from pytracer._errors import PytracerError
from pytracer.trace.event import NumericSummary, SourceRef, TraceEvent
from pytracer.trace.writer import EVENTS_FILENAME

_decoder = msgspec.json.Decoder(TraceEvent)


def iter_events(path: str | Path) -> tuple[list[TraceEvent], bool]:
    """Return (events, truncated). truncated=True when the final line was partial."""
    raw = Path(path).read_bytes()
    lines = raw.split(b"\n")
    events: list[TraceEvent] = []
    truncated = False
    last_index = len(lines) - 1
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            events.append(_decoder.decode(line))
        except msgspec.DecodeError as e:
            if i >= last_index - 1:
                truncated = True
                break
            raise PytracerError(f"{path}: corrupt event at line {i + 1}: {e}") from e
    return events, truncated


# Callsite identity: everything that must match for calls in different runs
# to be "the same call". Occurrence disambiguates repeats at one callsite.
CallKey = tuple[str, str, str | None, str | None, int | None, int]


@dataclass(slots=True)
class CallRecord:
    call_id: int
    module: str
    qualname: str
    tier: str
    ufunc_method: str | None
    source: SourceRef | None
    occurrence: int
    parent_call_id: int | None = None
    inputs: dict[str, NumericSummary | None] = field(default_factory=dict)
    outputs: dict[str, NumericSummary | None] = field(default_factory=dict)
    input_refs: dict[str, str] = field(default_factory=dict)
    output_refs: dict[str, str] = field(default_factory=dict)
    exception: str | None = None
    first_event_id: int = 0

    @property
    def key(self) -> CallKey:
        return (
            self.module,
            self.qualname,
            self.ufunc_method,
            self.source.file if self.source else None,
            self.source.lineno if self.source else None,
            self.occurrence,
        )

    @property
    def function(self) -> str:
        name = f"{self.module}.{self.qualname}"
        if self.ufunc_method and self.ufunc_method != "__call__":
            name += f".{self.ufunc_method}"
        return name


def assemble_calls(events: list[TraceEvent]) -> list[CallRecord]:
    calls: dict[int, CallRecord] = {}
    for ev in events:
        rec = calls.get(ev.call_id)
        if rec is None:
            rec = CallRecord(
                call_id=ev.call_id,
                module=ev.module,
                qualname=ev.qualname,
                tier=ev.tier,
                ufunc_method=ev.ufunc_method,
                source=ev.source,
                occurrence=ev.occurrence,
                parent_call_id=ev.parent_call_id,
                first_event_id=ev.event_id,
            )
            calls[ev.call_id] = rec
        if ev.phase == "input":
            name = ev.arg_name or f"Arg{len(rec.inputs)}"
            rec.inputs[name] = ev.summary
            if ev.payload_ref:
                rec.input_refs[name] = ev.payload_ref
        elif ev.phase == "output":
            name = ev.arg_name or "Ret"
            rec.outputs[name] = ev.summary
            if ev.payload_ref:
                rec.output_refs[name] = ev.payload_ref
        elif ev.phase == "exception":
            rec.exception = ev.note or "exception"
    return sorted(calls.values(), key=lambda r: r.first_event_id)


def load_run_calls(run_dir: str | Path) -> tuple[list[CallRecord], bool]:
    """Load calls for one run directory. Returns (calls, truncated)."""
    events_path = Path(run_dir) / EVENTS_FILENAME
    if not events_path.is_file():
        raise PytracerError(f"{run_dir}: no {EVENTS_FILENAME} found")
    events, truncated = iter_events(events_path)
    return assemble_calls(events), truncated
