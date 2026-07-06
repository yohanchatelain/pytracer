"""Control flow depends on an unseeded random draw: traced call counts
differ across runs, exercising divergence reporting."""

import numpy as np

rng = np.random.default_rng()
x = np.arange(10.0)
if rng.random() < 0.5:
    print(np.sum(x))
else:
    print(np.sum(x), np.sum(x * x))
