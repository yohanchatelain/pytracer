"""Per-process call context shared by all instrumentation tiers.

Provides:
- thread-safe event/call id generation,
- a contextvar call stack (parent linkage for nested traced calls),
- deterministic per-callsite occurrence counters (the alignment key),
- a reentrancy guard so pytracer's own numpy usage is never traced.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from pytracer.trace.event import SourceRef

_PYTRACER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_stack: ContextVar[tuple[int, ...]] = ContextVar("pytracer_call_stack", default=())
_inside: ContextVar[bool] = ContextVar("pytracer_inside", default=False)


class CallContext:
    def __init__(self, capture_backtrace: bool = True):
        self.capture_backtrace = capture_backtrace
        self._event_ids = itertools.count()
        self._call_ids = itertools.count()
        self._lock = threading.Lock()
        self._occurrences: dict[tuple, int] = {}

    def next_event_id(self) -> int:
        with self._lock:
            return next(self._event_ids)

    def next_call_id(self) -> int:
        with self._lock:
            return next(self._call_ids)

    def next_occurrence(self, callsite_key: tuple) -> int:
        with self._lock:
            n = self._occurrences.get(callsite_key, 0)
            self._occurrences[callsite_key] = n + 1
            return n

    def current_parent(self) -> int | None:
        stack = _stack.get()
        return stack[-1] if stack else None

    @contextmanager
    def pushed(self, call_id: int):
        token = _stack.set(_stack.get() + (call_id,))
        try:
            yield
        finally:
            _stack.reset(token)

    def inside(self) -> bool:
        return _inside.get()

    @contextmanager
    def guard(self):
        token = _inside.set(True)
        try:
            yield
        finally:
            _inside.reset(token)

    def caller_source(self) -> SourceRef | None:
        """First frame outside pytracer/wrapt/importlib machinery."""
        if not self.capture_backtrace:
            return None
        frame = sys._getframe(1)
        try:
            while frame is not None:
                filename = frame.f_code.co_filename
                if (
                    not filename.startswith(_PYTRACER_DIR)
                    and "wrapt" not in filename
                    and not filename.startswith("<frozen importlib")
                ):
                    return SourceRef(file=filename, lineno=frame.f_lineno)
                frame = frame.f_back
        finally:
            del frame
        return None
