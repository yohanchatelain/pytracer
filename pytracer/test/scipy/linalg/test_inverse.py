import numpy as np
import pytest
from scipy import linalg


def main():
    A = np.array([[1, 3, 5], [2, 5, 1], [2, 3, 8]])
    print(A)

    x = linalg.inv(A)
    print(x)

    x = A.dot(linalg.inv(A))  # double check
    print(x)


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
