import os
import pytest
import json
import tempfile


def get_config():
    return os.getenv("PYTRACER_CONFIG")


def get_pycfg(update):
    pycfg_env = get_config()
    fi = open(pycfg_env)
    pycfg = json.load(fi)
    pycfg.update(update)
    pycfg_path = os.path.dirname(pycfg_env)
    t = tempfile.NamedTemporaryFile(mode="w",
                                    dir=pycfg_path,
                                    suffix=".json")
    json.dump(pycfg, t)
    t.flush()
    os.environ["PYTRACER_CONFIG"] = os.path.join(t.name)
    return fi, t


@pytest.fixture
def turn_numpy_ufunc_on():
    pycfg_env = get_config()
    update = {"numpy": {"ufunc": True}}
    fori, ftmp = get_pycfg(update)

    yield

    os.environ["PYTRACER_CONFIG"] = pycfg_env
    fori.close()
    ftmp.close()


@pytest.fixture
def turn_numpy_ufunc_off():
    pycfg_env = get_config()
    update = {"numpy": {"ufunc": False}}
    fori, ftmp = get_pycfg(update)

    yield

    os.environ["PYTRACER_CONFIG"] = pycfg_env
    fori.close()
    ftmp.close()


@pytest.fixture
def cleandir(script_runner, tmp_path):
    os.chdir(tmp_path)
    yield
    ret = script_runner.run("pytracer", "--clean")
    assert ret.success
    os.chdir("..")


@pytest.fixture
def parse(script_runner):
    yield
    ret = script_runner.run("pytracer", "parse", "--online")
    assert ret.success


def pytest_addoption(parser):
    parser.addoption(
        "--nsamples", action="store", type=int, default=1,
        help="Number of samples to run"
    )


@pytest.fixture
def nsamples(request):
    return request.config.getoption("--nsamples")
