import numpy as np
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


sol = root(func2, [1, 1], jac=True, method='lm')
print(sol.x)
print(sol.fun)
