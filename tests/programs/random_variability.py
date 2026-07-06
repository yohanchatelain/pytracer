"""Per-run variability via an unseeded RNG (no perturbation backend needed)."""

import numpy as np

rng = np.random.default_rng()
x = 1e8 + rng.standard_normal(1000)
naive = np.mean(x * x) - np.mean(x) ** 2
print(float(naive))
