import os

import pytest


@pytest.fixture
def cleandir(bash, tmp_path):
    os.chdir(tmp_path)
    bash.auto_return_code_error = False
    yield
    bash.run_script("pytracer", ["clean"])
    assert(bash.last_return_code == 0)
    os.chdir("..")


@pytest.fixture
def parse(bash):
    bash.auto_return_code_error = False
    yield
    bash.run_script("pytracer", ["parse", "--online"])
    assert(bash.last_return_code == 0)


def pytest_addoption(parser):
    parser.addoption(
        "--nsamples", action="store", type=int, default=1,
        help="Number of samples to run"
    )


@pytest.fixture
def nsamples(request):
    return request.config.getoption("--nsamples")
