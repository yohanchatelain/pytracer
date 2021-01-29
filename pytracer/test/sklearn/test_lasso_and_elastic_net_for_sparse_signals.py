import pytest
import numpy as np
from sklearn import linear_model

# https://scikit-learn.org/stable/auto_examples/linear_model/plot_lasso_and_elasticnet.html#lasso-and-elastic-net-for-sparse-signals


def lasso_and_elastic_net_for_sparse_signals():
    # #############################################################################
    # Generate some sparse data to play with
    from sklearn.metrics import r2_score
    np.random.seed(42)

    n_samples, n_features = 50, 100
    X = np.random.randn(n_samples, n_features)

    # Decreasing coef w. alternated signs for visualization
    idx = np.arange(n_features)
    coef = (-1) ** idx * np.exp(-idx / 10)
    coef[10:] = 0  # sparsify coef
    y = np.dot(X, coef)

    # Add noise
    y += 0.01 * np.random.normal(size=n_samples)

    # Split data in train set and test set
    n_samples = X.shape[0]
    X_train, y_train = X[:n_samples // 2], y[:n_samples // 2]
    X_test, y_test = X[n_samples // 2:], y[n_samples // 2:]

    # #############################################################################
    # Lasso
    from sklearn.linear_model import Lasso

    alpha = 0.1
    lasso = linear_model.Lasso(alpha=alpha)

    y_pred_lasso = lasso.fit(X_train, y_train).predict(X_test)
    r2_score_lasso = r2_score(y_test, y_pred_lasso)
    print(lasso)
    print("r^2 on test data : %f" % r2_score_lasso)

    # #############################################################################
    # ElasticNet
    from sklearn.linear_model import ElasticNet

    enet = linear_model.ElasticNet(alpha=alpha, l1_ratio=0.7)

    y_pred_enet = enet.fit(X_train, y_train).predict(X_test)
    r2_score_enet = r2_score(y_test, y_pred_enet)
    print(enet)
    print("r^2 on test data : %f" % r2_score_enet)


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
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--module {__file__}")
        assert ret.success


if __name__ == "__main__":
    lasso_and_elastic_net_for_sparse_signals()
    print("End")
