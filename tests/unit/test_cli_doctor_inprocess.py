"""In-process CLI and doctor tests (subprocess integration tests exist too;
these give direct coverage and faster failure localization)."""

import pytest

from pytracer.cli.doctor import FAIL, OK, WARN, exit_code, format_checks, run_checks
from pytracer.cli.main import main


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_command_prints_help(in_tmp, capsys):
    assert main([]) == 0
    assert "pytracer" in capsys.readouterr().out


def test_init_and_config_show(in_tmp, capsys):
    assert main(["init"]) == 0
    assert (in_tmp / "pytracer.toml").is_file()
    assert main(["config", "show"]) == 0
    assert '"plugins"' in capsys.readouterr().out
    assert main(["config", "validate"]) == 0


def test_init_refuses_overwrite(in_tmp, capsys):
    assert main(["init"]) == 0
    assert main(["init"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["init", "--force"]) == 0


def test_plugins_commands(in_tmp, capsys):
    assert main(["plugins", "list"]) == 0
    assert "numpy" in capsys.readouterr().out
    assert main(["plugins", "targets", "numpy"]) == 0
    out = capsys.readouterr().out
    assert "numpy.linalg.solve" in out and "[ufunc]" in out
    assert main(["plugins", "targets"]) == 2  # missing name
    assert main(["plugins", "targets", "nonexistent"]) == 1


def test_check_missing_analysis(in_tmp, capsys):
    (in_tmp / "exp").mkdir()
    assert main(["check", "exp", "--min-sig-bits", "10"]) == 1
    assert "analyze" in capsys.readouterr().err


def test_check_without_thresholds_is_usage_error(in_tmp, capsys):
    (in_tmp / "exp").mkdir()
    assert main(["check", "exp"]) == 2


def test_suggest_targets_missing_coverage(in_tmp, capsys):
    (in_tmp / "exp").mkdir()
    assert main(["suggest-targets", "exp"]) == 1


def test_report_missing_analysis(in_tmp, capsys):
    (in_tmp / "exp").mkdir()
    assert main(["report", "exp"]) == 1


def test_clean_empty(in_tmp, capsys):
    assert main(["clean"]) == 0
    assert "nothing to clean" in capsys.readouterr().out


def test_run_missing_script(in_tmp, capsys):
    assert main(["run", "missing.py", "--plugins"]) == 1
    assert "not found" in capsys.readouterr().err


def test_script_args_split_on_double_dash(in_tmp):
    from pytracer.cli.main import build_parser  # noqa: F401 — parser importable

    # main() splits at "--" before argparse sees it
    script = in_tmp / "argecho.py"
    script.write_text("import sys\nassert sys.argv[1:] == ['--repeat', 'x'], sys.argv\n")
    assert main(["run", str(script), "--plugins", "--no-report",
                 "--", "--repeat", "x"]) == 0


# --- doctor -------------------------------------------------------------------


def test_doctor_checks_pass_here(in_tmp):
    checks = run_checks(in_tmp)
    by_name = {c["name"]: c for c in checks}
    assert by_name["numpy"]["status"] == OK
    assert by_name["config"]["status"] == OK  # no config file: defaults apply
    assert by_name["writable"]["status"] == OK
    assert exit_code(checks) in (0, 1)
    assert format_checks(checks)


def test_doctor_flags_invalid_config(in_tmp):
    (in_tmp / "pytracer.toml").write_text("[trace]\nmode = 'bogus'\n")
    checks = run_checks(in_tmp)
    by_name = {c["name"]: c for c in checks}
    assert by_name["config"]["status"] == FAIL
    assert exit_code(checks) == 1


def test_doctor_warns_without_perturbation_backend(in_tmp, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("VFC_", "VERROU_")) or key == "LD_PRELOAD":
            monkeypatch.delenv(key, raising=False)
    checks = run_checks(in_tmp)
    by_name = {c["name"]: c for c in checks}
    assert by_name["perturbation"]["status"] == WARN
