from pytracer.test.utils import trace
import pytest
from scipy.optimize import Bounds
import numpy as np
from scipy.optimize import minimize


def rosen(x):
    """The Rosenbrock function"""
    return sum(100.0*(x[1:]-x[:-1]**2.0)**2.0 + (1-x[:-1])**2.0)


def rosen_der(x):
    xm = x[1:-1]
    xm_m1 = x[:-2]
    xm_p1 = x[2:]
    der = np.zeros_like(x)
    der[1:-1] = 200*(xm-xm_m1**2) - 400*(xm_p1 - xm**2)*xm - 2*(1-xm)
    der[0] = -400*x[0]*(x[1]-x[0]**2) - 2*(1-x[0])
    der[-1] = 200*(x[-1]-x[-2]**2)
    return der


def main():
    ineq_cons = {'type': 'ineq',
                 'fun': lambda x: np.array([1 - x[0] - 2*x[1],
                                            1 - x[0]**2 - x[1],
                                            1 - x[0]**2 + x[1]]),
                 'jac': lambda x: np.array([[-1.0, -2.0],
                                            [-2*x[0], -1.0],
                                            [-2*x[0], 1.0]])}
    eq_cons = {'type': 'eq',
               'fun': lambda x: np.array([2*x[0] + x[1] - 1]),
               'jac': lambda x: np.array([2.0, 1.0])}

    bounds = Bounds([0, -0.5], [1.0, 2.0])
    x0 = np.array([0.5, 0])
    res = minimize(rosen, x0, method='SLSQP', jac=rosen_der,
                   constraints=[eq_cons, ineq_cons], options={
                       'ftol': 1e-9, 'disp': True},
                   bounds=bounds)

    print(res.x)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
