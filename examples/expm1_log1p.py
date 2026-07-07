"""Why expm1 and log1p exist.

For |x| << 1, exp(x) rounds to 1 + x + ... in doubles, so exp(x) - 1
cancels down to a handful of significant digits, quantized in steps of
ulp(1) = 2.2e-16. `numpy.expm1` computes the same quantity without ever
forming exp(x), keeping full precision. The same story applies to
log(1 + x) vs `numpy.log1p`.

Like the quadratic example, this cancellation is a *bias*: exp(x) involves
one rounding, so under input perturbation alone the naive result is bitwise
constant — reproducibly wrong. `_mca` simulates the stochastic rounding a
real backend (Verificarlo) applies to that intermediate, which the 1/x
amplification of the subtraction then blows up; the library functions leave
the same 1-ulp noise unamplified.

Run:
    pytracer run examples/expm1_log1p.py --repeat 5

Expected: the naive variants lose ~12 more bits than the library ones.
"""

import numpy as np

import pytracer

_rng = np.random.default_rng()  # unseeded: fresh stochastic rounding per run


def _mca(value):
    """Simulate MCA: one stochastic rounding of an intermediate (~1 ulp)."""
    return value * (1.0 + _rng.standard_normal() * 2.0**-52)


@pytracer.trace_function
def naive_expm1(x):
    return float(_mca(np.exp(x)) - 1.0)


@pytracer.trace_function
def library_expm1(x):
    return float(_mca(np.expm1(x)))


@pytracer.trace_function
def naive_log1p(x):
    return float(np.log(_mca(1.0 + x)))


@pytracer.trace_function
def library_log1p(x):
    return float(_mca(np.log1p(x)))


def main():
    rng = np.random.default_rng()  # unseeded: per-run relative perturbation
    x = 1e-12 * (1.0 + rng.standard_normal() * 1e-8)

    print(f"x               = {x:.17e}")
    print(f"naive expm1     = {naive_expm1(x):.17e}")
    print(f"library expm1   = {library_expm1(x):.17e}")
    print(f"naive log1p     = {naive_log1p(x):.17e}")
    print(f"library log1p   = {library_log1p(x):.17e}")


if __name__ == "__main__":
    main()
