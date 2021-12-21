import numpy as np
import pytest
from scipy.fft import dct, idct


def main():
    N = 100
    t = np.linspace(0, 20, N, endpoint=False)
    x = np.exp(-t/3)*np.cos(2*t)
    y = dct(x, norm='ortho')
    window = np.zeros(N)
    window[:20] = 1
    yr = idct(y*window, norm='ortho')
    s = np.sum(np.abs(x-yr)**2) / np.sum(np.abs(x)**2)
    print(s)

    window = np.zeros(N)
    window[:15] = 1
    yr = idct(y*window, norm='ortho')
    s = np.sum(np.abs(x-yr)**2) / np.sum(np.abs(x)**2)
    print(s)


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
