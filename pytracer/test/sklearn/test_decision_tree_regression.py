# print(__doc__)

# import the necessary commands and libraries
import os

import matplotlib.pyplot as plt
import numpy as np
import pytest

from sklearn.tree import DecisionTreeRegressor


def main():
    # Create a random dataset
    rng = np.random.RandomState(1)
    X = np.sort(5 * rng.rand(80, 1), axis=0)
    y = np.sin(X).ravel()
    y[::5] += 3 * (0.5 - rng.rand(16))

    # Fit regression model
    regr_1 = DecisionTreeRegressor(max_depth=2)
    regr_2 = DecisionTreeRegressor(max_depth=5)
    regr_1.fit(X, y)
    regr_2.fit(X, y)

    # Predict
    X_test = np.arange(0.0, 5.0, 0.01)[:, np.newaxis]
    y_1 = regr_1.predict(X_test)
    y_2 = regr_2.predict(X_test)

    # Plot the results
    # plt.figure()
    # plt.scatter(X, y, s=20, edgecolor="black",
    #             c="darkorange", label="data")
    # plt.plot(X_test, y_1, color="cornflowerblue",
    #          label="max_depth=2", linewidth=2)
    # plt.plot(X_test, y_2, color="yellowgreen", label="max_depth=5", linewidth=2)
    # plt.xlabel("data")
    # plt.ylabel("target")
    # plt.title("Decision Tree Regression")
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
def test_trace_only(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__} --test2=1")
    assert ret.success


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__} --test2=1")
        assert ret.success


if '__main__' == __name__:
    main()
