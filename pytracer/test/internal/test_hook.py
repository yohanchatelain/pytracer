
import pytest
import math
import inspect

from pytracer.test.utils import trace


def list_command():
    print('begin list_command')
    assert(not inspect.isbuiltin(math))
    print("HOOK:", math.sin)
    print("HOOK:", math.sin(1))
    print('end list_command')


list_command()


@pytest.mark.usefixtures("cleandir")
def test_trace_only_no_arg(bash):
    trace(__file__, bash)


@pytest.mark.usefixtures("cleandir")
def test_trace_only(bash):
    trace(__file__, bash, kwargs='--test2=1')


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, bash):
    for _ in range(nsamples):
        trace(__file__, bash)
