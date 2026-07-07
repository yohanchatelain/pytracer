"""Ill-conditioning: the Hilbert matrix amplifies input perturbations.

Solving Ax = b propagates relative input error to the solution multiplied
by cond(A). The 10x10 Hilbert matrix has cond ~ 1e13, so a 1e-12 relative
perturbation of b destroys essentially the whole solution, while the same
perturbation through a well-conditioned system is harmless. The algorithm
(LAPACK gesv) is identical in both cases — the *problem* is unstable.

Run:
    pytracer run examples/ill_conditioned_solve.py --repeat 5

Expected: `solve_hilbert` shows near-zero significant bits with large
amplification; `solve_well_conditioned` tracks the input perturbation.
"""

import numpy as np

import pytracer


def hilbert(n):
    i = np.arange(1, n + 1)
    return 1.0 / (i[:, None] + i[None, :] - 1.0)


@pytracer.trace_function
def solve_hilbert(b):
    return np.linalg.solve(hilbert(b.size), b)


@pytracer.trace_function
def solve_well_conditioned(b):
    A = np.eye(b.size) * 2.0 + np.diag(np.ones(b.size - 1) * 0.5, k=1)
    return np.linalg.solve(A, b)


def main():
    rng = np.random.default_rng()  # unseeded: per-run perturbation of b
    n = 10
    b = np.ones(n) * (1.0 + rng.standard_normal(n) * 1e-12)

    x_bad = solve_hilbert(b)
    x_good = solve_well_conditioned(b)
    print(f"cond(H_10) ~ {np.linalg.cond(hilbert(n)):.2e}")
    print(f"hilbert   x[0] = {x_bad[0]:.17e}")
    print(f"wellcond  x[0] = {x_good[0]:.17e}")


if __name__ == "__main__":
    main()
