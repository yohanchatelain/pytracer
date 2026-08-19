"""Polynomial evaluation near a multiple root (Demmel/Higham classic).

Evaluating p(x) = (x - 1)^7 from its expanded coefficients
(x^7 - 7x^6 + 21x^5 - ...) near x = 1 sums terms of magnitude ~35 that
cancel down to ~1e-28 — relative error is astronomical and the computed
curve is pure rounding noise. The factored form (x - 1)^7 is exact to
rounding.

Run:
    pytracer run examples/polynomial_eval.py --repeat 5

Expected: `expanded_poly` shows near-zero significant bits with large
amplification; `factored_poly` tracks the input perturbation.
"""

import numpy as np

import pytracer

# (x - 1)^7 expanded: binomial coefficients with alternating signs
COEFFS = np.array([1.0, -7.0, 21.0, -35.0, 35.0, -21.0, 7.0, -1.0])


@pytracer.trace_function
def expanded_poly(x):
    return float(np.polyval(COEFFS, x))


@pytracer.trace_function
def factored_poly(x):
    return float((x - 1.0) ** 7)


def main():
    rng = np.random.default_rng()  # unseeded: per-run perturbation of x
    x = (1.0 + 1e-4) * (1.0 + rng.standard_normal() * 1e-12)

    e = expanded_poly(x)
    f = factored_poly(x)
    print(f"x        = {x:.17f}")
    print(f"expanded = {e:.17e}")
    print(f"factored = {f:.17e}   (true ~ 1e-28)")


if __name__ == "__main__":
    main()
