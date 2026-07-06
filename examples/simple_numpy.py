"""Minimal deterministic example: with --perturb none this must show zero
variability (the determinism invariant)."""

import numpy as np

x = np.array([1.0, 2.0, 3.0])
print(np.sum(x))
