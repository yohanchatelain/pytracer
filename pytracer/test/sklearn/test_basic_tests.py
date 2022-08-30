from pytracer.test.utils import trace
import numpy as np
import pytest

from sklearn import linear_model


def basic_tests():
    reg = linear_model.LogisticRegression()
    reg.fit([[0, 0], [1, 1], [2, 2]], [0, 1, 2])
    print(reg.coef_)

    reg = linear_model.Ridge(alpha=.5)
    reg.fit([[0, 0], [0, 0], [1, 1]], [0, .1, 1])
    print(reg.coef_)
    print(reg.intercept_)

    reg = linear_model.RidgeCV(alphas=np.logspace(-6, 6, 13))
    reg.fit([[0, 0], [0, 0], [1, 1]], [0, .1, 1])
    print(reg.alpha_)

    reg = linear_model.Lasso(alpha=0.1)
    reg.fit([[0, 0], [1, 1]], [0, 1])
    reg.predict([[1, 1]])

    reg = linear_model.LassoLars(alpha=.1)
    reg.fit([[0, 0], [1, 1]], [0, 1])
    print(reg.coef_)

    reg = linear_model.LassoLars(alpha=.1)
    reg.fit([[0, 0], [1, 1]], [0, 1])
    reg.coef_

    # orthogonal_matching_pursuit()

    # Bayesian Ridge Regression is used for regression:
    X = [[0., 0.], [1., 1.], [2., 2.], [3., 3.]]
    Y = [0., 1., 2., 3.]
    reg = linear_model.BayesianRidge()
    reg.fit(X, Y)
    reg.predict([[1, 0.]])
    print(reg.coef_)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if __name__ == "__main__":
    import time
    print(time.localtime())
    basic_tests()
    print("End")
