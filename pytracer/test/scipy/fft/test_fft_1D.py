import sys

import numpy as np
import pytest
from scipy.fft import fft, fftfreq, fftshift, ifft, irfft, rfft
from scipy.signal import blackman


def main():
    x = np.array([1.0, 2.0, 1.0, -1.0, 1.5])
    y = fft(x)
    print(y)
    yinv = ifft(y)
    print('yinv', yinv)

    # Number of sample points
    N = 600
    # sample spacing
    T = 1.0 / 800.0
    x = np.linspace(0.0, N*T, N, endpoint=False)
    y = np.sin(50.0 * 2.0*np.pi*x) + 0.5*np.sin(80.0 * 2.0*np.pi*x)
    yf = fft(y)
    w = blackman(N)
    ywf = fft(y*w)
    xf = fftfreq(N, T)[:N//2]
    print(xf)

    freq = fftfreq(8, 0.125)
    print('freq', freq)

    x = np.arange(8)
    y = fftshift(x)
    print(y)

    # number of signal points
    N = 400
    # sample spacing
    T = 1.0 / 800.0
    x = np.linspace(0.0, N*T, N, endpoint=False)
    y = np.exp(50.0 * 1.j * 2.0*np.pi*x) + 0.5 * \
        np.exp(-80.0 * 1.j * 2.0*np.pi*x)
    yf = fft(y)
    xf = fftfreq(N, T)
    xf = fftshift(xf)
    yplot = fftshift(yf)
    print('yplot', yplot)

    x = np.array([1.0, 2.0, 1.0, -1.0, 1.5, 1.0])
    fft(x)
    yr = rfft(x)
    print(yr)
    irfft(yr)
    x = np.array([1.0, 2.0, 1.0, -1.0, 1.5])
    print(fft(x))
    yr = rfft(x)
    print(yr)

    y = irfft(yr)
    print(y)
    y = irfft(yr, n=len(x))
    print(y)


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
