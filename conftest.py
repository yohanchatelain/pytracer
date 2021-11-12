import os

import pytest


@pytest.fixture
def cleandir(script_runner, tmp_path):
    os.chdir(tmp_path)
    yield
    ret = script_runner.run("pytracer", "clean")
    assert(ret.success)
    os.chdir("..")


@pytest.fixture
def parse(script_runner):
    yield
    ret = script_runner.run("pytracer", "parse")
    assert(ret.success)


def pytest_addoption(parser):
    parser.addoption(
        "--nsamples", action="store", type=int, default=1,
        help="Number of samples to run"
    )


@pytest.fixture
def nsamples(request):
    return request.config.getoption("--nsamples")
