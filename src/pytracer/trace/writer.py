"""Append-safe trace capture.

Events are written as JSON lines (msgspec-encoded) so a crash of the traced
program loses at most the final partial line. Parquet conversion happens at
run finalization, never during capture.
"""

from __future__ import annotations

import threading
from pathlib import Path

import msgspec

from pytracer.trace.event import TraceEvent

EVENTS_FILENAME = "events.jsonl"
FLUSH_EVERY = 200


class TraceWriter:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / EVENTS_FILENAME
        self._encoder = msgspec.json.Encoder()
        self._lock = threading.Lock()
        self._fo = open(self.path, "ab")
        self._pending = 0
        self._closed = False
        self.n_events = 0

    def write_event(self, event: TraceEvent) -> None:
        line = self._encoder.encode(event) + b"\n"
        with self._lock:
            if self._closed:
                return
            self._fo.write(line)
            self.n_events += 1
            self._pending += 1
            if self._pending >= FLUSH_EVERY:
                self._fo.flush()
                self._pending = 0

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._fo.flush()
            self._fo.close()
