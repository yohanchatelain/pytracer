from pytracer.test.utils import trace
import numpy as np
import pytest
from scipy import linalg


def main():
    A = np.array([[1, 2], [3, 4]])
    print(A)

    b = np.array([[5], [6]])
    print(b)

    x = linalg.inv(A).dot(b)  # slow
    print(x)

    x = A.dot(linalg.inv(A).dot(b)) - b  # check
    print(x)

    x = np.linalg.solve(A, b)  # fast
    print(x)

    x = A.dot(np.linalg.solve(A, b)) - b  # check
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
