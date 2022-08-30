from pytracer.test.utils import trace
import pytest

import scipy.integrate as integrate
import scipy.special as special


def main():
    result = integrate.quad(lambda x: special.jv(2.5, x), 0, 4.5)
    print(result)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)


if '__main__' == __name__:
    main()
