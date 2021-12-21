import pytest
import numpy as np
import scipy


def main():

    r = np.random.random((3, 3))
    A = scipy.matrix(r)
    B = A+A - A*A
    print(B)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert ret.success


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__}")
        assert ret.success


if __name__ == '__main__':
    main()
