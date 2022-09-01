from pytracer.test.utils import trace
import pytest
from numpy import cosh, zeros, zeros_like
from scipy.optimize import root

# parameters
nx, ny = 75, 75
hx, hy = 1./(nx-1), 1./(ny-1)

P_left, P_right = 0, 0
P_top, P_bottom = 1, 0


def residual(P):
    d2x = zeros_like(P)
    d2y = zeros_like(P)

    d2x[1:-1] = (P[2:] - 2*P[1:-1] + P[:-2]) / hx/hx
    d2x[0] = (P[1] - 2*P[0] + P_left)/hx/hx
    d2x[-1] = (P_right - 2*P[-1] + P[-2])/hx/hx

    d2y[:, 1:-1] = (P[:, 2:] - 2*P[:, 1:-1] + P[:, :-2])/hy/hy
    d2y[:, 0] = (P[:, 1] - 2*P[:, 0] + P_bottom)/hy/hy
    d2y[:, -1] = (P_top - 2*P[:, -1] + P[:, -2])/hy/hy

    return d2x + d2y + 5*cosh(P).mean()**2


def main():
    # solve
    guess = zeros((nx, ny), float)
    sol = root(residual, guess, method='krylov', options={'disp': True})
    # sol = root(residual, guess, method='broyden2', options={'disp': True, 'max_rank': 50})
    # sol = root(residual, guess, method='anderson', options={'disp': True, 'M': 10})
    print('Residual: %g' % abs(residual(sol.x)).max())
    print(sol.x)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
