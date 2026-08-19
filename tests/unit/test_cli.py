import subprocess
import sys


def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_help(tmp_path):
    proc = run_cli(["--help"], tmp_path)
    assert proc.returncode == 0
    assert "pytracer" in proc.stdout


def test_version(tmp_path):
    import pytracer

    proc = run_cli(["--version"], tmp_path)
    assert proc.returncode == 0
    assert pytracer.__version__ in proc.stdout


def test_init_and_config_show(tmp_path):
    assert run_cli(["init"], tmp_path).returncode == 0
    assert (tmp_path / "pytracer.toml").is_file()
    proc = run_cli(["config", "show"], tmp_path)
    assert proc.returncode == 0
    assert '"plugins"' in proc.stdout


def test_config_validate_bad_config(tmp_path):
    (tmp_path / "pytracer.toml").write_text("[trace]\nmode = 'bogus'\n")
    proc = run_cli(["config", "validate"], tmp_path)
    assert proc.returncode == 1
    assert "mode" in proc.stderr


def test_plugins_list_and_targets(tmp_path):
    proc = run_cli(["plugins", "list"], tmp_path)
    assert proc.returncode == 0
    assert "numpy" in proc.stdout
    proc = run_cli(["plugins", "targets", "numpy"], tmp_path)
    assert proc.returncode == 0
    assert "numpy.linalg.solve" in proc.stdout
    assert "[ufunc]" in proc.stdout


def test_doctor_runs_without_config(tmp_path):
    proc = run_cli(["doctor"], tmp_path)
    assert proc.returncode == 0
    assert "Pytracer doctor" in proc.stdout
