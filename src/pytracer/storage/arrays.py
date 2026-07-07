"""Per-run array payload storage for element-wise significance analysis.

Arrays are stored as individual .npy files under ``<run_dir>/arrays/`` and
referenced from events via ``payload_ref`` (relative path). One file per
write keeps capture crash-safe: a dying run loses at most the array being
written. The ``payload_ref`` indirection means a chunked/compressed backend
(Zarr) can replace this one without touching the event schema.

Eligibility:
- mode "never":  no store is created.
- mode "auto":   numeric ndarrays with size <= threshold elements.
- mode "always": all numeric ndarrays.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

ARRAYS_DIRNAME = "arrays"
DEFAULT_THRESHOLD = 100_000  # elements; float64 -> 800 KB per array

_SANITIZE = re.compile(r"[^A-Za-z0-9_.-]")


class ArrayStore:
    def __init__(self, run_dir: str | Path, mode: str = "auto",
                 threshold: int = DEFAULT_THRESHOLD):
        if mode not in ("auto", "always"):
            raise ValueError(f"ArrayStore mode must be 'auto' or 'always', got {mode!r}")
        self.run_dir = Path(run_dir)
        self.mode = mode
        self.threshold = threshold
        self._dir = self.run_dir / ARRAYS_DIRNAME
        self.n_stored = 0
        self.n_skipped = 0

    def _eligible(self, value: object) -> bool:
        if not isinstance(value, np.ndarray):
            return False
        if value.dtype == object or value.dtype.kind in "USVmM":
            return False
        if value.size == 0:
            return False
        if self.mode == "auto" and value.size > self.threshold:
            return False
        return True

    def maybe_store(self, call_id: int, phase: str, arg_name: str | None,
                    value: object) -> str | None:
        """Store *value* if eligible; return the payload_ref (relative path)."""
        try:
            if not self._eligible(value):
                if isinstance(value, np.ndarray):
                    self.n_skipped += 1
                return None
            self._dir.mkdir(parents=True, exist_ok=True)
            safe_arg = _SANITIZE.sub("_", arg_name or "arg")
            name = f"{call_id:06d}-{phase}-{safe_arg}.npy"
            np.save(self._dir / name, value, allow_pickle=False)
            self.n_stored += 1
            return f"{ARRAYS_DIRNAME}/{name}"
        except Exception:
            # Storage failure must never break the traced program.
            self.n_skipped += 1
            return None


def load_array(run_dir: str | Path, payload_ref: str) -> np.ndarray | None:
    """Load a stored array by its payload_ref; None if missing/unreadable."""
    path = Path(run_dir) / payload_ref
    try:
        return np.load(path, allow_pickle=False)
    except (OSError, ValueError):
        return None


def make_array_store(run_dir: str | Path, mode: str,
                     threshold: int = DEFAULT_THRESHOLD) -> ArrayStore | None:
    if mode == "never":
        return None
    return ArrayStore(run_dir, mode=mode, threshold=threshold)
