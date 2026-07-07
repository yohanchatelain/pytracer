"""Element-wise significant digits across runs.

Given the same array captured in N runs, compute per-element
``sig = -log2(std/|mean|)`` (clipped to [0, 53]) and summarize the
distribution. This is the real measurement that ``sig(mean)`` only
approximates: element permutations across runs have identical summary
statistics but near-zero element-wise significance.

Estimator: relative-std ("general" style). The CNH estimator from the
`significantdigits` package can be swapped in behind this interface.
"""

from __future__ import annotations

import numpy as np

SIG_CAP_BITS = 53.0


def elementwise_sig(stack: np.ndarray) -> dict | None:
    """Per-element significance distribution for a (n_runs, *shape) stack.

    Returns {"min", "p05", "median", "n_elements", "n_undefined"} in bits,
    or None when nothing is measurable.
    """
    if stack.ndim < 1 or stack.shape[0] < 2:
        return None
    runs = np.atleast_2d(stack.reshape(stack.shape[0], -1)).astype(np.float64, copy=False)

    with np.errstate(all="ignore"):
        mean = runs.mean(axis=0)
        std = runs.std(axis=0)
        sig = np.full(mean.shape, np.nan)

        finite = np.isfinite(mean) & np.isfinite(std)
        exact = finite & (std == 0.0)
        sig[exact] = SIG_CAP_BITS
        zero_mean = finite & (std > 0.0) & (mean == 0.0)
        sig[zero_mean] = 0.0
        measurable = finite & (std > 0.0) & (mean != 0.0)
        sig[measurable] = np.clip(
            -np.log2(std[measurable] / np.abs(mean[measurable])), 0.0, SIG_CAP_BITS
        )

    valid = sig[np.isfinite(sig)]
    n_undefined = int(sig.size - valid.size)
    if valid.size == 0:
        return None
    return {
        "min": float(np.min(valid)),
        "p05": float(np.percentile(valid, 5)),
        "median": float(np.median(valid)),
        "n_elements": int(valid.size),
        "n_undefined": n_undefined,
    }


def stack_arrays(arrays: list[np.ndarray | None]) -> np.ndarray | None:
    """Stack per-run arrays into (n_runs, *shape); None on any mismatch."""
    if any(a is None for a in arrays) or len(arrays) < 2:
        return None
    shapes = {a.shape for a in arrays}  # type: ignore[union-attr]
    if len(shapes) != 1:
        return None  # control flow changed the data shape across runs
    if arrays[0].dtype.kind == "c":  # type: ignore[union-attr]
        arrays = [np.abs(a) for a in arrays]  # type: ignore[arg-type]
    try:
        return np.stack(arrays)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
