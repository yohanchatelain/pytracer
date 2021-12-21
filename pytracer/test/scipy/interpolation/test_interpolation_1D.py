import numpy as np
import pytest
from scipy.interpolate import interp1d


def main():
    x = np.linspace(0, 10, num=11, endpoint=True)
    y = np.cos(-x**2/9.0)
    f = interp1d(x, y)
    f2 = interp1d(x, y, kind='cubic')

    xnew = np.linspace(0, 10, num=41, endpoint=True)
    print(f(xnew))
    print(f2(xnew))

    x = np.linspace(0, 10, num=11, endpoint=True)
    y = np.cos(-x**2/9.0)
    f1 = interp1d(x, y, kind='nearest')
    f2 = interp1d(x, y, kind='previous')
    f3 = interp1d(x, y, kind='next')

    xnew = np.linspace(0, 10, num=1001, endpoint=True)
    print(f1(xnew))
    print(f2(xnew))
    print(f3(xnew))


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
