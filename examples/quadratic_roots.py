"""Catastrophic cancellation in the quadratic formula.

For x^2 + bx + c with b >> c, the small root is -c/b + O(c^2/b^3). The
textbook formula computes it as (-b + sqrt(b^2 - 4c)) / 2 — the difference
of two nearly equal numbers ~b, cancelling almost every significant digit.
The stable form multiplies by the conjugate so no cancellation occurs:
    x_small = 2c / (-b - sqrt(b^2 - 4c))

A subtlety this example demonstrates: with b = 1e8 the cancellation is a
pure *bias* — sqrt(b^2 - 4c) involves a single rounding, so under mere
input perturbation the naive root is bitwise identical across runs:
reproducibly wrong, invisible to variance-based analysis. Real stochastic
arithmetic (Verificarlo MCA) perturbs that intermediate rounding itself;
`_mca` below simulates exactly that (one ~1-ulp stochastic rounding of the
square root), standing in for a backend when running on IEEE hardware.

Run:
    pytracer run examples/quadratic_roots.py --repeat 5

Expected: `naive_small_root` ranks far above `stable_small_root`
(large amplification, few significant bits).
"""

import math

import numpy as np

import pytracer

_rng = np.random.default_rng()  # unseeded: fresh stochastic rounding per run


def _mca(value):
    """Simulate MCA: one stochastic rounding of an intermediate (~1 ulp)."""
    return value * (1.0 + _rng.standard_normal() * 2.0**-52)


@pytracer.trace_function
def naive_small_root(b, c):
    return (-b + _mca(math.sqrt(b * b - 4.0 * c))) / 2.0


@pytracer.trace_function
def stable_small_root(b, c):
    return (2.0 * c) / (-b - _mca(math.sqrt(b * b - 4.0 * c)))


def main():
    rng = np.random.default_rng()  # unseeded: per-run input perturbation
    b = 1.0e8
    c = 1.0 * (1.0 + rng.standard_normal() * 1e-10)

    exact = -c / b  # to first order
    naive = naive_small_root(b, c)
    stable = stable_small_root(b, c)
    print(f"exact ~ {exact:.17e}")
    print(f"naive   {naive:.17e}  (rel err {abs((naive - exact) / exact):.1e})")
    print(f"stable  {stable:.17e}  (rel err {abs((stable - exact) / exact):.1e})")


if __name__ == "__main__":
    main()
