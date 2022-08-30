# https://scikit-learn.org/stable/auto_examples/decomposition/plot_pca_iris.html#sphx-glr-auto-examples-decomposition-plot-pca-iris-py

from pytracer.test.utils import trace
import pytest


def pca():
    # Code source: Gaël Varoquaux
    # License: BSD 3 clause

    import matplotlib.pyplot as plt
    import numpy as np
    from mpl_toolkits.mplot3d import Axes3D

    from sklearn import datasets, decomposition

    np.random.seed(5)

    centers = [[1, 1], [-1, -1], [1, -1]]
    iris = datasets.load_iris()
    X = iris.data
    y = iris.target

    fig = plt.figure(1, figsize=(4, 3))
    plt.clf()
    ax = Axes3D(fig, rect=[0, 0, .95, 1], elev=48, azim=134)

    plt.cla()
    pca = decomposition.PCA()
    pca.fit(X)
    X = pca.transform(X)
    print(pca.explained_variance_)

    # for name, label in [('Setosa', 0), ('Versicolour', 1), ('Virginica', 2)]:
    #     ax.text3D(X[y == label, 0].mean(),
    #               X[y == label, 1].mean() + 1.5,
    #               X[y == label, 2].mean(), name,
    #               horizontalalignment='center',
    #               bbox=dict(alpha=.5, edgecolor='w', facecolor='w'))
    # # Reorder the labels to have colors matching the cluster results
    # y = np.choose(y, [1, 2, 0]).astype(np.float)
    # ax.scatter(X[:, 0], X[:, 1], X[:, 2], c=y, cmap=plt.cm.nipy_spectral,
    #            edgecolor='k')

    # ax.w_xaxis.set_ticklabels([])
    # ax.w_yaxis.set_ticklabels([])
    # ax.w_zaxis.set_ticklabels([])

    # plt.show()


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if __name__ == '__main__':
    pca()
