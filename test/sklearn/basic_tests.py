import numpy as np
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


if __name__ == "__main__":
    basic_tests()
