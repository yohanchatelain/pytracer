from pytracer.test.utils import trace
import numpy as np
import pytest
from scipy import linalg


def main():
    A = np.array([[1, 3, 5], [2, 5, 1], [2, 3, 8]])
    print(A)

    x = linalg.inv(A)
    print(x)

    x = A.dot(linalg.inv(A))  # double check
    print(x)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
