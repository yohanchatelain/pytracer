import numpy as np
import pytest
from scipy.fft import ifftn


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
def test_trace_only(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__} --test2=1")
    assert ret.success


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__} --test2=1")
        assert ret.success


if '__main__' == __name__:
    main()
