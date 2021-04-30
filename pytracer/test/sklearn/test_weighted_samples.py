import pytest

# https://scikit-learn.org/stable/auto_examples/linear_model/plot_sgd_weighted_samples.html#sphx-glr-auto-examples-linear-model-plot-sgd-weighted-samples-py


def weighted_samples():
    import numpy as np
    import matplotlib.pyplot as plt
    from sklearn import linear_model

    # we create 20 points
    np.random.seed(0)
    X = np.r_[np.random.randn(10, 2) + [1, 1], np.random.randn(10, 2)]
    y = [1] * 10 + [-1] * 10
    sample_weight = 100 * np.abs(np.random.randn(20))
    # and assign a bigger weight to the last 10 samples
    sample_weight[:10] *= 10

    # plot the weighted data points
    xx, yy = np.meshgrid(np.linspace(-4, 5, 500), np.linspace(-4, 5, 500))
    plt.figure()
    plt.scatter(X[:, 0], X[:, 1], c=y, s=sample_weight, alpha=0.9,
                cmap=plt.cm.bone, edgecolor='black')

    # fit the unweighted model
    clf = linear_model.SGDClassifier(alpha=0.01, max_iter=100)
    clf.fit(X, y)
    Z = clf.decision_function(np.c_[xx.ravel(), yy.ravel()])
    Z = Z.reshape(xx.shape)
    no_weights = plt.contour(xx, yy, Z, levels=[0], linestyles=['solid'])

    # fit the weighted model
    clf = linear_model.SGDClassifier(alpha=0.01, max_iter=100)
    clf.fit(X, y, sample_weight=sample_weight)
    Z = clf.decision_function(np.c_[xx.ravel(), yy.ravel()])
    Z = Z.reshape(xx.shape)
    samples_weights = plt.contour(xx, yy, Z, levels=[0], linestyles=['dashed'])

    # plt.legend([no_weights.collections[0], samples_weights.collections[0]],
    #         ["no weights", "with weights"], loc="lower left")

    # plt.xticks(())
    # plt.yticks(())
    # plt.show()


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
    weighted_samples()
