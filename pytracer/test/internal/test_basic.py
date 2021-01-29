#!/usr/bin/python3

import pytest
import os
import math
import numpy as np
import argparse


def main():

    import sys
    print(sys.argv)

    parser = argparse.ArgumentParser("test")
    parser.add_argument('--test1')
    parser.add_argument('--test2', required=True)
    args = parser.parse_args()
    print("args", args)

    import pytracer.test.internal.test_hook as hook
    print("list module of hook")
    hook.list_module()

    print(math.pi)

    print("math.sin", math.sin)
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
    print(np.random)
    print(np.random.uniform(size=10))
    print(np.minimum)
    print(np.minimum.accumulate)

    print("Test finished")

# Pytests


@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir")
def test_trace_only_no_arg_ufunc_on(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__}")
    assert not ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir")
def test_trace_only_no_arg_ufunc_off(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__}")
    assert not ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir")
def test_trace_only_ufunc_on(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__} --test2=1")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir")
def test_trace_only_ufunc_off(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--module {__file__} --test2=1")
    assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_on", "cleandir", "parse")
def test_trace_parse_ufunc_on(nsamples, script_runner):
    for i in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--module {__file__} --test2=1")
        assert ret.success


@pytest.mark.usefixtures("turn_numpy_ufunc_off", "cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--module {__file__} --test2=1")
        assert ret.success


if '__main__' == __name__:
    main()
