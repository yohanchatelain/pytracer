import numpy as np
import pytest
from scipy import interpolate

from pytracer.test.utils import trace


def main():
    x_edges, y_edges = np.mgrid[-1:1:21j, -1:1:21j]
    x = x_edges[:-1, :-1] + np.diff(x_edges[:2, 0])[0] / 2.
    y = y_edges[:-1, :-1] + np.diff(y_edges[0, :2])[0] / 2.
    z = (x+y) * np.exp(-6.0*(x*x+y*y))

    xnew_edges, ynew_edges = np.mgrid[-1:1:71j, -1:1:71j]
    xnew = xnew_edges[:-1, :-1] + np.diff(xnew_edges[:2, 0])[0] / 2.
    ynew = ynew_edges[:-1, :-1] + np.diff(ynew_edges[0, :2])[0] / 2.
    tck = interpolate.bisplrep(x, y, z, s=0)
    znew = interpolate.bisplev(xnew[:, 0], ynew[0, :], tck)

    print(znew)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
