"""Non-associativity of floating-point summation.

Summing the same ill-scaled data in a different order gives a different
result — this is exactly the effect stochastic-arithmetic environments
amplify. A naive left-to-right running sum accumulates rounding at the
magnitude of the running total; `math.fsum` (Shewchuk, exactly rounded) is
immune to ordering; NumPy's pairwise summation sits in between.

The data is identical in every run — only the order changes. `math.fsum`
is exactly rounded and therefore order-invariant: it must show the full 53
bits, making it the perfect control. Any variability in the naive running
sum is pure rounding non-associativity.

Run:
    pytracer run examples/summation_order.py --repeat 5

Expected: `exact_fsum` at 53 bits; `naive_running_sum` far below it.
"""

import math

import numpy as np

import pytracer


@pytracer.trace_function
def naive_running_sum(x):
    total = 0.0
    for v in x:
        total += v
    return total


@pytracer.trace_function
def pairwise_sum(x):
    return float(np.sum(x))


@pytracer.trace_function
def exact_fsum(x):
    return math.fsum(x.tolist())


def main():
    rng = np.random.default_rng()  # unseeded: per-run shuffle only
    x = np.concatenate([
        np.array([1e14, -1e14]),
        np.random.default_rng(12345).standard_normal(20_000) * 1e4,
    ])
    rng.shuffle(x)  # same multiset every run, different order

    print(f"naive    {naive_running_sum(x):.17e}")
    print(f"pairwise {pairwise_sum(x):.17e}")
    print(f"fsum     {exact_fsum(x):.17e}")


if __name__ == "__main__":
    main()
