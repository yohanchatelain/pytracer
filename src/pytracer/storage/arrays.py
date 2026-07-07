"""Per-run array payload storage for element-wise significance analysis.

Arrays are stored one file per argument under ``<run_dir>/arrays/`` and
referenced from events via ``payload_ref`` (relative path). One file per
write keeps capture crash-safe: a dying run loses at most the array being
written.

Backends (``array_backend`` config):
- "npy":  numpy .npy files — zero extra dependencies, uncompressed.
- "zarr": zstd-compressed Zarr stores — needs the [arrays] extra.
- "auto": zarr when importable, else npy (default).

``load_array`` dispatches on the payload_ref suffix, so runs written with
either backend read back transparently.

Eligibility (``store_arrays`` config):
- mode "never":  no store is created.
- mode "auto":   numeric ndarrays with size <= threshold elements.
- mode "always": all numeric ndarrays.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import numpy as np

ARRAYS_DIRNAME = "arrays"
DEFAULT_THRESHOLD = 100_000  # elements; float64 -> 800 KB per array

_SANITIZE = re.compile(r"[^A-Za-z0-9_.-]")


def resolve_backend(backend: str = "auto") -> str:
    if backend == "auto":
        return "zarr" if importlib.util.find_spec("zarr") is not None else "npy"
    if backend not in ("npy", "zarr"):
        raise ValueError(f"array backend must be auto|npy|zarr, got {backend!r}")
    if backend == "zarr" and importlib.util.find_spec("zarr") is None:
        raise ValueError("array_backend = 'zarr' but zarr is not installed "
                         "(pip install 'pytracer[arrays]')")
    return backend


class ArrayStore:
    def __init__(self, run_dir: str | Path, mode: str = "auto",
                 threshold: int = DEFAULT_THRESHOLD, backend: str = "auto"):
        if mode not in ("auto", "always"):
            raise ValueError(f"ArrayStore mode must be 'auto' or 'always', got {mode!r}")
        self.run_dir = Path(run_dir)
        self.mode = mode
        self.threshold = threshold
        self.backend = resolve_backend(backend)
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
            stem = f"{call_id:06d}-{phase}-{safe_arg}"
            if self.backend == "zarr":
                import zarr

                name = f"{stem}.zarr"
                zarr.save(str(self._dir / name), np.ascontiguousarray(value))
            else:
                name = f"{stem}.npy"
                np.save(self._dir / name, value, allow_pickle=False)
            self.n_stored += 1
            return f"{ARRAYS_DIRNAME}/{name}"
        except Exception:
            # Storage failure must never break the traced program.
            self.n_skipped += 1
            return None


def load_array(run_dir: str | Path, payload_ref: str) -> np.ndarray | None:
    """Load a stored array by its payload_ref; None if missing/unreadable.

    Dispatches on the ref suffix so npy- and zarr-written runs coexist.
    """
    path = Path(run_dir) / payload_ref
    try:
        if payload_ref.endswith(".zarr"):
            import zarr

            if not path.exists():
                return None
            loaded = zarr.load(str(path))
            return np.asarray(loaded) if loaded is not None else None
        return np.load(path, allow_pickle=False)
    except (OSError, ValueError, ImportError):
        return None


def make_array_store(run_dir: str | Path, mode: str,
                     threshold: int = DEFAULT_THRESHOLD,
                     backend: str = "auto") -> ArrayStore | None:
    if mode == "never":
        return None
    return ArrayStore(run_dir, mode=mode, threshold=threshold, backend=backend)
