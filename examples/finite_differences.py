"""Step-size dilemma in finite differences.

The forward difference (f(x+h) - f(x)) / h has truncation error O(h) and
roundoff error O(eps/h): shrinking h past ~sqrt(eps) makes the subtraction
cancel catastrophically. With h = 1e-13 the estimate of sin'(1) is
roundoff-dominated noise; a central difference at the optimal
h = cbrt(eps) stays accurate.

Run:
    pytracer run examples/finite_differences.py --repeat 5

Expected: `forward_diff_tiny_h` shows few significant bits;
`central_diff_optimal_h` tracks the input perturbation.
"""

import math

import numpy as np

import pytracer

EPS = np.finfo(np.float64).eps


@pytracer.trace_function
def forward_diff_tiny_h(x):
    h = 1e-15  # far below sqrt(eps): cancellation dominates
    return (math.sin(x + h) - math.sin(x)) / h


@pytracer.trace_function
def central_diff_optimal_h(x):
    h = EPS ** (1.0 / 3.0)
    return (math.sin(x + h) - math.sin(x - h)) / (2.0 * h)


def main():
    rng = np.random.default_rng()  # unseeded: per-run perturbation of x
    x = 1.0 * (1.0 + rng.standard_normal() * 1e-8)
    exact = math.cos(x)

    fwd = forward_diff_tiny_h(x)
    ctr = central_diff_optimal_h(x)
    print(f"exact    {exact:.17f}")
    print(f"forward  {fwd:.17f}  (err {abs(fwd - exact):.1e})")
    print(f"central  {ctr:.17f}  (err {abs(ctr - exact):.1e})")


if __name__ == "__main__":
    main()
