"""The shared recording engine used by all wrapper tiers.

A recorded call: input events → original call → output events (or exception
event + re-raise). The wrapped function's result is returned unchanged.
Recording failures never propagate into the traced program.
"""

from __future__ import annotations

import functools
import inspect
import time

from pytracer.instrumentation.call_context import CallContext
from pytracer.trace.event import SCHEMA_VERSION, NumericSummary, SourceRef, TraceEvent
from pytracer.trace.summary import summarize_value
from pytracer.trace.writer import TraceWriter

_active_recorder: Recorder | None = None

_BIND_WITH_WRAPPED = object()  # sentinel: bind arguments against `wrapped`


def get_active_recorder() -> Recorder | None:
    return _active_recorder


def set_active_recorder(recorder: Recorder | None) -> None:
    global _active_recorder
    _active_recorder = recorder


@functools.lru_cache(maxsize=2048)
def _signature_of(fn):
    return inspect.signature(fn)


def _cached_signature(fn):
    # inspect.signature is ~70us per call; hot wrappers call it per event.
    try:
        return _signature_of(fn)
    except TypeError:  # unhashable callable: fall back uncached
        return inspect.signature(fn)


class Recorder:
    def __init__(
        self,
        writer: TraceWriter,
        run_id: str,
        *,
        capture_backtrace: bool = True,
        mode: str = "summary",
        array_store=None,
        taint_outputs: bool = False,
    ):
        self.writer = writer
        self.run_id = run_id
        self.mode = mode
        self.array_store = array_store
        # When True (--instrument taint), outputs of traced calls are wrapped
        # as TracedArray so the T3 protocol re-seeds at every known boundary.
        self.taint_outputs = taint_outputs
        self.context = CallContext(capture_backtrace=capture_backtrace)

    # -- event emission -----------------------------------------------------

    def _summary(self, value: object) -> NumericSummary | None:
        if self.mode == "metadata":
            return None
        return summarize_value(value)

    def _make_event(
        self,
        *,
        event_id: int,
        call_id: int,
        parent: int | None,
        occurrence: int,
        phase: str,
        module: str,
        qualname: str,
        tier: str,
        ufunc_method: str | None,
        arg_name: str | None,
        value: object = None,
        source: SourceRef | None,
        inplace: bool = False,
        note: str | None = None,
        with_payload: bool = True,
    ) -> TraceEvent:
        summary = self._summary(value) if with_payload else None
        payload_ref = None
        if with_payload and self.array_store is not None and phase in ("input", "output"):
            payload_ref = self.array_store.maybe_store(
                call_id,
                phase,
                arg_name,
                value,
                fingerprint=summary.fingerprint if summary is not None else None,
            )
        if payload_ref is not None:
            payload_kind = "array_ref"
        elif summary is not None:
            payload_kind = "summary"
        else:
            payload_kind = "none"
        return TraceEvent(
            schema_version=SCHEMA_VERSION,
            run_id=self.run_id,
            event_id=event_id,
            call_id=call_id,
            parent_call_id=parent,
            occurrence=occurrence,
            phase=phase,  # type: ignore[arg-type]
            module=module,
            qualname=qualname,
            tier=tier,  # type: ignore[arg-type]
            ufunc_method=ufunc_method,
            arg_name=arg_name,
            inplace=inplace,
            payload_kind=payload_kind,  # type: ignore[arg-type]
            summary=summary,
            payload_ref=payload_ref,
            source=source,
            note=note,
            ts_ns=time.monotonic_ns(),
        )

    def _emit(self, **kwargs) -> None:
        event = self._make_event(event_id=self.context.next_event_id(), **kwargs)
        self.writer.write_event(event)

    def _emit_items(self, items, *, phase: str, **common) -> None:
        """Summarize and write one call phase as a single event batch."""
        items = list(items)
        event_ids = self.context.next_event_ids(len(items))
        events = [
            self._make_event(
                event_id=event_id,
                phase=phase,
                arg_name=name,
                value=value,
                **common,
            )
            for event_id, (name, value) in zip(event_ids, items, strict=True)
        ]
        self.writer.write_events(events)

    @staticmethod
    def _bind_arguments(bind_with, args, kwargs) -> dict[str, object]:
        if bind_with is not None:
            try:
                sig = _cached_signature(bind_with)
                bound = sig.bind(*args, **kwargs)
                arguments = dict(bound.arguments)
                arguments.pop("self", None)
                return arguments
            except (ValueError, TypeError):
                pass
        named = {f"Arg{i}": v for i, v in enumerate(args)}
        named.update(kwargs)
        return named

    @staticmethod
    def _output_items(result: object) -> list[tuple[str, object]]:
        if isinstance(result, tuple):
            return [(f"Ret{i}", v) for i, v in enumerate(result)]
        return [("Ret", result)]

    # -- the wrapper protocol -------------------------------------------------

    def record_call(
        self,
        *,
        module: str,
        qualname: str,
        tier: str,
        wrapped,
        args,
        kwargs,
        ufunc_method: str | None = None,
        inplace: bool = False,
        bind_with=_BIND_WITH_WRAPPED,
    ):
        if bind_with is _BIND_WITH_WRAPPED:
            bind_with = wrapped
        ctx = self.context
        if ctx.inside():
            # Reentrant use of a traced function from inside pytracer itself
            # (e.g. numpy calls made while computing a summary): pass through.
            return wrapped(*args, **kwargs)

        try:
            with ctx.guard():
                source = ctx.caller_source()
                callsite_key = (
                    module,
                    qualname,
                    ufunc_method,
                    source.file if source else None,
                    source.lineno if source else None,
                )
                call_id, occurrence = ctx.next_call(callsite_key)
                parent = ctx.current_parent()
                common = dict(
                    call_id=call_id,
                    parent=parent,
                    occurrence=occurrence,
                    module=module,
                    qualname=qualname,
                    tier=tier,
                    ufunc_method=ufunc_method,
                    source=source,
                    inplace=inplace,
                )
                self._emit_items(
                    self._bind_arguments(bind_with, args, kwargs).items(),
                    phase="input",
                    **common,
                )
        except Exception:
            # Never let recording break the traced call: run it untraced.
            return wrapped(*args, **kwargs)

        try:
            with ctx.pushed(call_id):
                result = wrapped(*args, **kwargs)
        except Exception as exc:
            try:
                with ctx.guard():
                    self._emit(
                        phase="exception",
                        arg_name=None,
                        note=f"{type(exc).__name__}: {exc}",
                        with_payload=False,
                        **common,
                    )
            except Exception:
                pass
            raise

        try:
            with ctx.guard():
                self._emit_items(self._output_items(result), phase="output", **common)
        except Exception:
            pass
        if self.taint_outputs and tier != "t3":
            try:
                from pytracer.instrumentation.tracer_array import rewrap

                result = rewrap(result)
            except Exception:
                pass
        return result
