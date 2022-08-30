from pytracer.test.utils import trace
import numpy as np
import pytest
from scipy import misc, signal


def main():
    image = misc.face(gray=True).astype(np.float32)
    derfilt = np.array([1.0, -2, 1.0], dtype=np.float32)
    ck = signal.cspline2d(image, 8.0)
    deriv = (signal.sepfir2d(ck, derfilt, [1]) +
             signal.sepfir2d(ck, [1], derfilt))
    print(deriv)

    laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    deriv2 = signal.convolve2d(ck, laplacian, mode='same', boundary='symm')
    print(deriv2)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
