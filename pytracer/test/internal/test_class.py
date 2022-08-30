import pytest
import numpy as np
import scipy

from pytracer.test.utils import trace


def main():

    r = np.random.random((3, 3))
    A = scipy.matrix(r)
    B = A+A - A*A
    print(B)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if __name__ == '__main__':
    main()
