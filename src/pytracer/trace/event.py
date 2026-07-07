"""Schema-versioned trace events (msgspec structs).

Every artifact pytracer writes carries SCHEMA_VERSION. Events are the wire
format; analysis reassembles them into calls (see trace.reader.CallRecord).
"""

from __future__ import annotations

from typing import Literal

import msgspec

SCHEMA_VERSION = "2.0.0"

Phase = Literal["input", "output", "exception"]
PayloadKind = Literal["none", "summary", "array_ref"]
Tier = Literal["t1", "t2", "t3", "t4"]


class SourceRef(msgspec.Struct, frozen=True, omit_defaults=True):
    file: str
    lineno: int


class NumericSummary(msgspec.Struct, omit_defaults=True):
    dtype: str
    shape: tuple[int, ...]
    size: int
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    l2_norm: float | None = None
    linf_norm: float | None = None
    nan_count: int = 0
    inf_count: int = 0
    zero_count: int = 0
    subnormal_count: int = 0
    cancellation: float | None = None
    fingerprint: str | None = None


class TraceEvent(msgspec.Struct, omit_defaults=True):
    schema_version: str
    run_id: str
    event_id: int
    call_id: int
    occurrence: int
    phase: Phase
    module: str
    qualname: str
    tier: Tier = "t1"
    parent_call_id: int | None = None
    ufunc_method: str | None = None
    arg_name: str | None = None
    inplace: bool = False
    payload_kind: PayloadKind = "none"
    summary: NumericSummary | None = None
    payload_ref: str | None = None
    source: SourceRef | None = None
    note: str | None = None  # exception text on phase == "exception"
    ts_ns: int | None = None  # monotonic nanoseconds within the run
