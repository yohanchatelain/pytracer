from pytracer.test.utils import trace
import numpy as np
import pytest
from scipy.optimize import root


def func(x):
    return x + 2 * np.cos(x)


sol = root(func, 0.3)
print(sol.x)
print(sol.fun)


def func2(x):
    f = [x[0] * np.cos(x[1]) - 4,
         x[1]*x[0] - x[1] - 5]
    df = np.array([[np.cos(x[1]), -x[0] * np.sin(x[1])],
                   [x[1], x[0] - 1]])
    return f, df


def main():
    sol = root(func2, [1, 1], jac=True, method='lm')
    print(sol.x)
    print(sol.fun)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
