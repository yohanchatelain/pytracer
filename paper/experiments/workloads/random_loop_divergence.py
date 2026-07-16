"""Harsher control-flow divergence: the number of traced calls per run is
drawn from a random loop count, so runs disagree not just on one branch
but on the length of the call sequence."""

import numpy as np

rng = np.random.default_rng()
x = np.arange(50.0)

total = 0.0
for _ in range(rng.integers(3, 12)):
    total += float(np.sum(x))
    x = x * 1.0001

if total > 0:
    print(np.mean(x), total)
