import numpy as np
import pytest
from scipy import linalg


def main():
    A = np.array([[1, 2], [3, 4]])
    print(A)

    b = np.array([[5], [6]])
    print(b)

    x = linalg.inv(A).dot(b)  # slow
    print(x)

    x = A.dot(linalg.inv(A).dot(b)) - b  # check
    print(x)

    x = np.linalg.solve(A, b)  # fast
    print(x)

    x = A.dot(np.linalg.solve(A, b)) - b  # check
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
