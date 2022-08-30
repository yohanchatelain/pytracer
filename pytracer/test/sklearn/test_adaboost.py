# https://scikit-learn.org/stable/auto_examples/ensemble/plot_adaboost_regression.html#sphx-glr-auto-examples-ensemble-plot-adaboost-regression-py

# Author: Noel Dawe <noel.dawe@gmail.com>
#
# License: BSD 3 clause

# importing necessary libraries
from pytracer.test.utils import trace
import os

import numpy as np
import pytest

from sklearn.ensemble import AdaBoostRegressor
#import matplotlib.pyplot as plt
from sklearn.tree import DecisionTreeRegressor


def adaboost():
    # Create the dataset
    rng = np.random.RandomState(1)
    X = np.linspace(0, 6, 100)[:, np.newaxis]
    y = np.sin(X).ravel() + np.sin(6 * X).ravel() + \
        rng.normal(0, 0.1, X.shape[0])

    # Fit regression model
    regr_1 = DecisionTreeRegressor(max_depth=4)

    regr_2 = AdaBoostRegressor(DecisionTreeRegressor(max_depth=4),
                               n_estimators=300, random_state=rng)

    regr_1.fit(X, y)
    regr_2.fit(X, y)

    # Predict
    y_1 = regr_1.predict(X)
    y_2 = regr_2.predict(X)

    # Plot the results
    # plt.figure()
    # plt.scatter(X, y, c="k", label="training samples")
    # plt.plot(X, y_1, c="g", label="n_estimators=1", linewidth=2)
    # plt.plot(X, y_2, c="r", label="n_estimators=300", linewidth=2)
    # plt.xlabel("data")
    # plt.ylabel("target")
    # plt.title("Boosted Decision Tree Regression")
    # plt.legend()
    # plt.show()

    # def get_name_fig():
    #     name = f"fig-0.pdf"
    #     i = 0
    #     while os.path.isfile(name):
    #         i += 1
    #         name = f"fig-{i}.pdf"
    #     return name


# name = get_name_fig()
# plt.savefig(name)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if __name__ == "__main__":
    adaboost()
