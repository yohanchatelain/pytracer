import numpy as np
import pytest
from scipy import linalg

from pytracer.test.utils import trace


def main():

    A = np.array([[1, 2], [3, 4]])
    print(A)

    det = linalg.det(A)
    print(det)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
