import pytest
import numpy as np
from sklearn import linear_model


def multitask_lasso():

    rng = np.random.RandomState(42)

    n_samples, n_features, n_tasks = 100, 30, 40
    n_relevant_features = 5
    coef = np.zeros((n_tasks, n_features))
    times = np.linspace(0, 2 * np.pi, n_tasks)
    for k in range(n_relevant_features):
        coef[:, k] = np.sin((1. + rng.randn(1)) * times + 3 * rng.randn(1))

    X = rng.randn(n_samples, n_features)
    Y = np.dot(X, coef.T) + rng.randn(n_samples, n_tasks)

    coef_lasso_ = np.array([linear_model.Lasso(
        alpha=0.5).fit(X, y).coef_ for y in Y.T])
    coef_multi_task_lasso_ = linear_model.MultiTaskLasso(
        alpha=1.).fit(X, Y).coef_


@pytest.mark.xfail
@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir")
def test_trace_only_ufunc_on(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__}")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir")
def test_trace_only_ufunc_off(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__}")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir", "parse")
def test_trace_parse(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__}")
    assert ret.success


if __name__ == "__main__":
    multitask_lasso()
