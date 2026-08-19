"""E7 footprint workload: a few thousand traced calls so per-event storage
costs dominate fixed per-file overhead."""

import numpy as np

rng = np.random.default_rng()
x = np.arange(100.0) * (1.0 + rng.normal(scale=1e-12))

total = 0.0
for _ in range(2000):
    total += float(np.sum(x))
print(total)
