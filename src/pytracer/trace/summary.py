"""Numeric summaries of traced values.

Summaries never raise. Fingerprinting copies at most
``max_fingerprint_bytes``; dtype conversion and non-finite filtering in the
exact array summary may allocate larger temporary arrays. Non-numeric values
summarize to None.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from pytracer.trace.event import NumericSummary

MAX_FINGERPRINT_BYTES = 1_000_000


def summarize_value(value: object) -> NumericSummary | None:
    """Summarize a scalar or NumPy array; return None for non-numeric values."""
    try:
        if isinstance(value, bool | int | float | complex | np.generic):
            return _summarize_scalar(value)
        elif isinstance(value, np.ndarray):
            array = value
        else:
            return None
        if array.dtype == object or array.dtype.kind in "USVmM":
            return None
        return _summarize_array(array)
    except Exception:
        # A summary failure must never break the traced program.
        return None


def _summarize_scalar(value: object) -> NumericSummary | None:
    """Summarize one numeric scalar without invoking array reductions.

    Scalar inputs and scalar return values are common in boundary tracing.
    Sending them through ``np.mean``, ``np.std``, ``np.linalg.norm``, and the
    counting reductions costs far more than the wrapped operation itself.
    """
    array = np.asarray(value)
    if array.dtype == object or array.dtype.kind in "USVmM":
        return None

    summary = NumericSummary(dtype=str(array.dtype), shape=(), size=1)
    item = array.item()
    if array.dtype.kind == "c":
        numeric = float(abs(item))
        real_dtype = np.abs(array).dtype
    elif array.dtype.kind == "b":
        numeric = float(bool(item))
        real_dtype = None
    else:
        numeric = float(item)
        real_dtype = array.dtype if array.dtype.kind == "f" else None

    summary.zero_count = int(numeric == 0.0)
    if math.isnan(numeric):
        summary.nan_count = 1
    elif math.isinf(numeric):
        summary.inf_count = 1
    else:
        if real_dtype is not None and numeric != 0.0:
            summary.subnormal_count = int(abs(numeric) < np.finfo(real_dtype).tiny)
        summary.mean = numeric
        summary.std = 0.0
        summary.min = numeric
        summary.max = numeric
        magnitude = abs(numeric)
        summary.l2_norm = magnitude
        summary.linf_norm = magnitude

    summary.fingerprint = array_fingerprint(array)
    return summary


def _summarize_array(array: np.ndarray) -> NumericSummary:
    dtype = str(array.dtype)
    shape = tuple(int(d) for d in array.shape)
    size = int(array.size)
    summary = NumericSummary(dtype=dtype, shape=shape, size=size)
    if size == 0:
        return summary

    if array.dtype.kind == "c":
        values = np.abs(array)
    elif array.dtype.kind == "b":
        values = array.astype(np.float64)
    else:
        values = array

    summary.zero_count = int(np.count_nonzero(values == 0))

    if values.dtype.kind == "f":
        finite = np.isfinite(values)
        n_finite = int(np.count_nonzero(finite))
        summary.nan_count = int(np.count_nonzero(np.isnan(values)))
        summary.inf_count = size - n_finite - summary.nan_count
        tiny = np.finfo(values.dtype).tiny
        with np.errstate(invalid="ignore"):
            absv = np.abs(values)
            summary.subnormal_count = int(np.count_nonzero((absv > 0) & (absv < tiny)))
    else:
        # integer/bool data cannot hold NaN/Inf/subnormals: skip those passes
        finite = None
        n_finite = size

    if n_finite:
        if finite is not None and n_finite != size:
            fv = values[finite]
        else:
            fv = values
        fv64 = fv.astype(np.float64, copy=False)
        summary.mean = float(np.mean(fv64))
        summary.std = float(np.std(fv64))
        summary.min = float(np.min(fv64))
        summary.max = float(np.max(fv64))
        # |x|_inf from the extrema already computed: saves an abs pass
        summary.linf_norm = max(abs(summary.min), abs(summary.max))
        summary.l2_norm = float(np.linalg.norm(fv64.ravel()))

    summary.fingerprint = array_fingerprint(array)
    return summary


def array_fingerprint(array: np.ndarray, max_bytes: int = MAX_FINGERPRINT_BYTES) -> str | None:
    """Stable blake2b fingerprint over at most *max_bytes* of the array.

    Small arrays are hashed in full. Large contiguous arrays are hashed over
    an evenly strided sample view (bounded copy). Large non-contiguous
    arrays are not fingerprinted — sampling them would require copying the
    whole array first.
    """
    try:
        header = f"{array.dtype}|{array.shape}|".encode()
        if array.nbytes <= max_bytes:
            data = np.ascontiguousarray(array).tobytes()
        elif array.flags.c_contiguous or array.flags.f_contiguous:
            flat = array.reshape(-1)  # view: array is contiguous
            step = max(1, int(np.ceil(array.nbytes / max_bytes)))
            data = np.ascontiguousarray(flat[::step]).tobytes()
        else:
            return None
        return hashlib.blake2b(header + data, digest_size=16).hexdigest()
    except Exception:
        return None
