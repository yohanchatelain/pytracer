import pytest
import numpy as np
from matplotlib import pyplot as plt
from sklearn import linear_model, datasets
import os


def robust_linear_regression():
    n_samples = 1000
    n_outliers = 50

    np.random.seed(0)

    X, y, coef = datasets.make_regression(n_samples=n_samples, n_features=1,
                                          n_informative=1, noise=10,
                                          coef=True, random_state=0)

    # Add outlier data
    X[:n_outliers] = 3 + 0.5 * np.random.normal(size=(n_outliers, 1))
    y[:n_outliers] = -3 + 10 * np.random.normal(size=n_outliers)

    # Fit line using all data
    lr = linear_model.LinearRegression()
    lr.fit(X, y)

    # Robustly fit linear model with RANSAC algorithm
    ransac = linear_model.RANSACRegressor()
    ransac.fit(X, y)
    inlier_mask = ransac.inlier_mask_
    outlier_mask = np.logical_not(inlier_mask)

    # Predict data of estimated models
    line_X = np.arange(X.min(), X.max())[:, np.newaxis]
    line_y = lr.predict(line_X)
    line_y_ransac = ransac.predict(line_X)

    # Compare estimated coefficients
    print("Estimated coefficients (true, linear regression, RANSAC):")
    print(coef, lr.coef_, ransac.estimator_.coef_)

    # lw = 2
    # plt.scatter(X[inlier_mask], y[inlier_mask], color='yellowgreen', marker='.',
    #             label='Inliers')
    # plt.scatter(X[outlier_mask], y[outlier_mask], color='gold', marker='.',
    #             label='Outliers')
    # plt.plot(line_X, line_y, color='navy', linewidth=lw, label='Linear regressor')
    # plt.plot(line_X, line_y_ransac, color='cornflowerblue', linewidth=lw,
    #          label='RANSAC regressor')
    # plt.legend(loc='lower right')
    # plt.xlabel("Input")
    # plt.ylabel("Response")

    # def get_name_fig():
    #     name = f"fig-0.pdf"
    #     i = 0
    #     while os.path.isfile(name):
    #         i += 1
    #         name = f"fig-{i}.pdf"
    #     return name

    # name = get_name_fig()
    # plt.savefig(name)

    # plt.show()


@pytest.mark.xfail
@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir")
def test_trace_only_ufunc_on(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir")
def test_trace_only_ufunc_off(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__}")
        assert ret.success


if __name__ == "__main__":
    robust_linear_regression()
