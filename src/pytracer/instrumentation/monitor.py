"""Tier T4 — runtime monitor built on sys.monitoring (PEP 669, Python 3.12+).

Structure only, never operand values:
- per-line execution counts for the target script's own code
  (cross-run count differences localize control-flow divergence), and
- a census of calls to C callables made from the target script's code —
  including untraced numpy functions — which feeds coverage accounting and
  target suggestion.

On interpreters without sys.monitoring the monitor is a no-op and says so.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

MONITOR_FILENAME = "monitor.json"


class Monitor:
    def __init__(self, scope_dir: str | Path, run_dir: str | Path):
        self.scope_dir = str(Path(scope_dir).resolve())
        self.run_dir = Path(run_dir)
        self.line_counts: Counter[str] = Counter()
        self.c_calls: Counter[str] = Counter()
        self.active = False
        self.available = hasattr(sys, "monitoring")
        self._tool_id = None

    def _in_scope(self, filename: str) -> bool:
        return (
            filename.startswith(self.scope_dir)
            and "site-packages" not in filename
            and ".pytracer" not in filename
        )

    def start(self) -> None:
        if not self.available:
            return
        mon = sys.monitoring
        self._tool_id = mon.PROFILER_ID
        try:
            mon.use_tool_id(self._tool_id, "pytracer")
        except ValueError:
            self.available = False  # someone else (a profiler) owns the id
            return

        def on_line(code, line_number):
            if not self._in_scope(code.co_filename):
                return mon.DISABLE
            self.line_counts[f"{code.co_filename}:{line_number}"] += 1
            return None

        def on_call(code, instruction_offset, callable_obj, arg0):
            if not self._in_scope(code.co_filename):
                return mon.DISABLE
            if hasattr(callable_obj, "__code__"):
                return None  # Python function: structure comes from wrappers
            mod = getattr(callable_obj, "__module__", None) or ""
            name = getattr(callable_obj, "__qualname__", None) or getattr(
                callable_obj, "__name__", repr(type(callable_obj))
            )
            self.c_calls[f"{mod}.{name}" if mod else name] += 1
            return None

        mon.register_callback(self._tool_id, mon.events.LINE, on_line)
        mon.register_callback(self._tool_id, mon.events.CALL, on_call)
        mon.set_events(self._tool_id, mon.events.LINE | mon.events.CALL)
        self.active = True

    def stop(self) -> None:
        if self.active and self._tool_id is not None:
            mon = sys.monitoring
            mon.set_events(self._tool_id, 0)
            mon.register_callback(self._tool_id, mon.events.LINE, None)
            mon.register_callback(self._tool_id, mon.events.CALL, None)
            mon.free_tool_id(self._tool_id)
            self.active = False
        self._write()

    def _write(self) -> None:
        payload = {
            "available": self.available,
            "line_counts": dict(self.line_counts),
            "c_calls": dict(self.c_calls),
        }
        (self.run_dir / MONITOR_FILENAME).write_text(json.dumps(payload, indent=2))
