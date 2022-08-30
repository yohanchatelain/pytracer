from pytracer.test.utils import trace
import pytest
from numpy import cosh, eye, mgrid, zeros, zeros_like
from scipy.optimize import root
from scipy.sparse import kron, spdiags
from scipy.sparse.linalg import LinearOperator, spilu

# parameters
nx, ny = 75, 75
hx, hy = 1./(nx-1), 1./(ny-1)

P_left, P_right = 0, 0
P_top, P_bottom = 1, 0


def get_preconditioner():
    """Compute the preconditioner M"""
    diags_x = zeros((3, nx))
    diags_x[0, :] = 1/hx/hx
    diags_x[1, :] = -2/hx/hx
    diags_x[2, :] = 1/hx/hx
    Lx = spdiags(diags_x, [-1, 0, 1], nx, nx)

    diags_y = zeros((3, ny))
    diags_y[0, :] = 1/hy/hy
    diags_y[1, :] = -2/hy/hy
    diags_y[2, :] = 1/hy/hy
    Ly = spdiags(diags_y, [-1, 0, 1], ny, ny)

    J1 = kron(Lx, eye(ny)) + kron(eye(nx), Ly)

    # Now we have the matrix `J_1`. We need to find its inverse `M` --
    # however, since an approximate inverse is enough, we can use
    # the *incomplete LU* decomposition

    J1_ilu = spilu(J1)

    # This returns an object with a method .solve() that evaluates
    # the corresponding matrix-vector product. We need to wrap it into
    # a LinearOperator before it can be passed to the Krylov methods:

    M = LinearOperator(shape=(nx*ny, nx*ny), matvec=J1_ilu.solve)
    return M


def solve(preconditioning=True):
    """Compute the solution"""
    count = [0]

    def residual(P):
        count[0] += 1

        d2x = zeros_like(P)
        d2y = zeros_like(P)

        d2x[1:-1] = (P[2:] - 2*P[1:-1] + P[:-2])/hx/hx
        d2x[0] = (P[1] - 2*P[0] + P_left)/hx/hx
        d2x[-1] = (P_right - 2*P[-1] + P[-2])/hx/hx

        d2y[:, 1:-1] = (P[:, 2:] - 2*P[:, 1:-1] + P[:, :-2])/hy/hy
        d2y[:, 0] = (P[:, 1] - 2*P[:, 0] + P_bottom)/hy/hy
        d2y[:, -1] = (P_top - 2*P[:, -1] + P[:, -2])/hy/hy

        return d2x + d2y + 5*cosh(P).mean()**2

    # preconditioner
    if preconditioning:
        M = get_preconditioner()
    else:
        M = None

    # solve
    guess = zeros((nx, ny), float)

    sol = root(residual, guess, method='krylov',
               options={'disp': True,
                        'jac_options': {'inner_M': M}})
    print('Residual', abs(residual(sol.x)).max())
    print('Evaluations', count[0])

    return sol.x


def main():
    sol = solve(preconditioning=True)
    print(sol)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
