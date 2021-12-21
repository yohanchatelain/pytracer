
import pytest
import math
import inspect


def list_command():
    print('begin list_command')
    assert(not inspect.isbuiltin(math))
    print("HOOK:", math.sin)
    print("HOOK:", math.sin(1))
    print('end list_command')


list_command()


@pytest.mark.usefixtures("cleandir")
def test_trace_only_no_arg(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__}")
    assert ret.success


@pytest.mark.usefixtures("cleandir")
def test_trace_only(script_runner):
    ret = script_runner.run("pytracer", "trace",
                            f"--command {__file__} --test2=1")
    assert ret.success


@pytest.mark.usefixtures("cleandir", "parse")
def test_trace_parse(nsamples, script_runner):
    for _ in range(nsamples):
        ret = script_runner.run("pytracer", "trace",
                                f"--command {__file__}")
        assert ret.success
