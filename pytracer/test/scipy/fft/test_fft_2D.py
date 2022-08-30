import numpy as np
import pytest
from scipy.fft import ifftn

from pytracer.test.utils import trace


def main():
    N = 30
    xf = np.zeros((N, N))
    xf[0, 5] = 1
    xf[0, N-5] = 1
    Z = ifftn(xf)
    print(Z)

    xf = np.zeros((N, N))
    xf[5, 0] = 1
    xf[N-5, 0] = 1
    Z = ifftn(xf)
    print(Z)

    xf = np.zeros((N, N))
    xf[5, 10] = 1
    xf[N-5, N-10] = 1
    Z = ifftn(xf)
    print(Z)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
