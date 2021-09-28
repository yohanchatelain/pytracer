# https://scikit-learn.org/stable/auto_examples/linear_model/plot_omp.html#sphx-glr-auto-examples-linear-model-plot-omp-py

import pytest
import numpy as np
from sklearn.linear_model import OrthogonalMatchingPursuit
from sklearn.linear_model import OrthogonalMatchingPursuitCV
from sklearn.datasets import make_sparse_coded_signal

np.random.seed(0)


def orthogonal_matching_pursuit():

    n_components, n_features = 512, 100
    n_nonzero_coefs = 17

    # generate the data

    # y = Xw
    # |x|_0 = n_nonzero_coefs

    y, X, w = make_sparse_coded_signal(n_samples=1,
                                       n_components=n_components,
                                       n_features=n_features,
                                       n_nonzero_coefs=n_nonzero_coefs,
                                       random_state=0)

    idx, = w.nonzero()

    # distort the clean signal
    y_noisy = y + 0.05 * np.random.randn(len(y))

    # # plot the sparse signal
    # plt.figure(figsize=(7, 7))
    # plt.subplot(4, 1, 1)
    # plt.xlim(0, 512)
    # plt.title("Sparse signal")
    # plt.stem(idx, w[idx], use_line_collection=True)

    # plot the noise-free reconstruction
    omp = OrthogonalMatchingPursuit(n_nonzero_coefs=n_nonzero_coefs)
    omp.fit(X, y)
    coef = omp.coef_
    idx_r, = coef.nonzero()
    # plt.subplot(4, 1, 2)
    # plt.xlim(0, 512)
    # plt.title("Recovered signal from noise-free measurements")
    # plt.stem(idx_r, coef[idx_r], use_line_collection=True)

    # plot the noisy reconstruction
    omp.fit(X, y_noisy)
    coef = omp.coef_
    idx_r, = coef.nonzero()
    # plt.subplot(4, 1, 3)
    # plt.xlim(0, 512)
    # plt.title("Recovered signal from noisy measurements")
    # plt.stem(idx_r, coef[idx_r], use_line_collection=True)

    # plot the noisy reconstruction with number of non-zeros set by CV
    omp_cv = OrthogonalMatchingPursuitCV()
    omp_cv.fit(X, y_noisy)
    coef = omp_cv.coef_
    idx_r, = coef.nonzero()
    # plt.subplot(4, 1, 4)
    # plt.xlim(0, 512)
    # plt.title("Recovered signal from noisy measurements with CV")
    # plt.stem(idx_r, coef[idx_r], use_line_collection=True)

    # plt.subplots_adjust(0.06, 0.04, 0.94, 0.90, 0.20, 0.38)
    # plt.suptitle('Sparse signal recovery with Orthogonal Matching Pursuit',
    #             fontsize=16)
    # plt.show()


@pytest.mark.slow
@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir")
def test_trace_only_ufunc_on(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert not ret.success


@pytest.mark.slow
@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir")
def test_trace_only_ufunc_off(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert ret.success


@pytest.mark.slow
@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__}")
        assert ret.success


if __name__ == "__main__":
    orthogonal_matching_pursuit()
