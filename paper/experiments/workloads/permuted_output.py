"""E5 workload: a traced function whose output is the same multiset of
values in a different (random) order on every run.

Summary statistics of the output are permutation-invariant up to
summation-order rounding, so the sig(mean) proxy reports the output as
highly stable; element-wise significant digits see the near-total loss.
"""

import numpy as np

import pytracer

rng = np.random.default_rng()  # unseeded: permutation differs per run
VALUES = np.linspace(1.0, 2.0, 100)


@pytracer.trace_function
def permuted_pipeline(x):
    return rng.permutation(x)


@pytracer.trace_function
def stable_pipeline(x):
    return x * 2.0


out = permuted_pipeline(VALUES)
ref = stable_pipeline(VALUES)
print(float(out.mean()), float(ref.mean()))
