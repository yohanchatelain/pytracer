import pytest
import pytracer.test.test_data as test_data


all_modules_list = []
all_modules_list.extend(test_data.get_test_path(test_data.internal_tests))
all_modules_list.extend(test_data.get_test_path(test_data.sklearn_tests))


@pytest.mark.parametrize("module",
                         test_data.get_test_path(test_data.internal_tests,
                                                 include="basic"))
def test_pytracer_trace_basic_argument(script_runner, module):
    ret = script_runner.run("pytracer", "trace",
                            "--module ", f"{module} --test2=1")
    assert ret.success


@pytest.mark.parametrize("module",
                         test_data.get_test_path(test_data.internal_tests,
                                                 exclude="basic"))
def test_pytracer_trace_internal(script_runner, module):
    ret = script_runner.run("pytracer", "trace", "--module ", module)
    assert ret.success


@pytest.mark.parametrize("module",
                         test_data.get_test_path(test_data.sklearn_tests))
def test_pytracer_trace_sklearn(script_runner, module):
    ret = script_runner.run("pytracer", "trace", "--module ", module)
    assert ret.success
