# https://scikit-learn.org/stable/auto_examples/linear_model/plot_multi_task_lasso_support.html#sphx-glr-auto-examples-linear-model-plot-multi-task-lasso-support-py

from pytracer.test.utils import trace
import numpy as np
import pytest

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


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if __name__ == "__main__":
    multitask_lasso()
