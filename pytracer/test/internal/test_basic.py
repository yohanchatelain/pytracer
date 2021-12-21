#!/usr/bin/python3

import argparse
import math

import numpy as np
import pytest


def f(x, y, z):
    sum_ = 0
    if (h := x-y) < 0:
        for i in range(x):
            sum_ += i/h
        else:
            sum_ += sum_

    if x < y:
        z = z * x
        return z+sum_
    else:
        z = z * y
        return z+sum_


def show(name, function):
    print(f"{name} {function} {hex(id(function))}")


def main():

    try:
        x = 1/0
    except ZeroDivisionError as e:
        print(e)
    else:
        print(x)
    finally:
        print("Division done")

    import sys
    print(sys.argv)

    parser = argparse.ArgumentParser("test")
    parser.add_argument('--test1')
    parser.add_argument('--test2', required=True)
    args = parser.parse_args()
    print("args", args)

    import pytracer.test.internal.test_hook as hook
    print("list command of hook")
    hook.list_command()

    print(math.pi)

    show("math.sin", math.sin)
    for i in range(50):
        x = math.sin(i+np.random.uniform(-0.01, 0.01))
        # print(x)

    for i in range(50):
        x = np.sin(i+np.random.uniform(-0.01, 0.01))
        print(x)

    print(math.sin(1))
    print(math.cos(1))
    print(math.tan(1))

    print(np.float16(1))
    print("NUMPY", np.sin(1))
    mat = np.matrix([[1, 2, 3], [5, 6, 7], [8, 9, 10]])
    print(np.linalg.norm(mat))
    show("random", np.random)
    print(np.random.uniform(size=10))
    show("minimum", np.minimum)
    show("minimum.accumulate", np.minimum.accumulate)

    print("Test finished")

# Pytests


@pytest.mark.usefixtures("cleandir")
def test_trace_only_no_arg(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert(not ret.success)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__} --test2=1")
    assert(ret.success)


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__} --test2=1")
        assert(ret.success)


if '__main__' == __name__:
    main()
