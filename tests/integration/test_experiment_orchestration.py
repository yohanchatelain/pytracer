"""Experiment orchestration edge cases: failures, continue-on-error."""

import sys

import pytest

from pytracer._errors import ExperimentError
from pytracer.config.schema import PytracerConfig
from pytracer.experiment import run_experiment

pytestmark = pytest.mark.integration


def config_for(tmp_path):
    config = PytracerConfig()
    config.storage.output_dir = str(tmp_path / "out")
    return config


def test_missing_script_raises(tmp_path):
    with pytest.raises(ExperimentError, match="not found"):
        run_experiment(config=config_for(tmp_path), script=str(tmp_path / "no.py"),
                       script_args=[], target_specs=[], repeat=1)


def test_bad_repeat_raises(tmp_path):
    script = tmp_path / "p.py"
    script.write_text("print('hi')\n")
    with pytest.raises(ExperimentError, match="repeat"):
        run_experiment(config=config_for(tmp_path), script=str(script),
                       script_args=[], target_specs=[], repeat=0)


def test_failure_stops_by_default(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys\nsys.exit(3)\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=[], repeat=3)
    assert [r.exit_code for r in result.runs] == [3]  # stopped after first
    assert any("stopping" in w for w in result.warnings)


def test_continue_on_error_runs_all(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys\nsys.exit(3)\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=[], repeat=3,
                            continue_on_error=True)
    assert [r.exit_code for r in result.runs] == [3, 3, 3]
    assert len(result.failed_runs) == 3


def test_script_args_forwarded(tmp_path):
    script = tmp_path / "args.py"
    script.write_text(
        "import sys\nassert sys.argv[1:] == ['a', '--b'], sys.argv\nprint('ok')\n"
    )
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=["a", "--b"], target_specs=[], repeat=1)
    assert result.runs[0].exit_code == 0


def test_perturb_env_templated_per_run(tmp_path):
    script = tmp_path / "env.py"
    script.write_text(
        "import os, sys\n"
        "expected = 'seed-' + os.environ['PYTRACER_RUN_ID']\n"
        "sys.exit(0 if os.environ['MY_SEED'] == expected else 9)\n"
    )
    config = config_for(tmp_path)
    config.perturb.env = {"MY_SEED": "seed-{run_id}"}
    result = run_experiment(config=config, script=str(script),
                            script_args=[], target_specs=[], repeat=2)
    assert [r.exit_code for r in result.runs] == [0, 0]


def test_bootstrap_exit_code_mirrors_sysexit(tmp_path):
    script = tmp_path / "code.py"
    script.write_text("raise SystemExit(7)\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=[], repeat=1)
    assert result.runs[0].exit_code == 7


def test_run_dirs_and_metadata_created_even_on_failure(tmp_path):
    script = tmp_path / "boom.py"
    script.write_text("raise RuntimeError('kaboom')\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=["numpy.sum"], repeat=1)
    run = result.runs[0]
    assert run.exit_code == 1
    meta = (run.run_dir / "metadata.json").read_text()
    assert "kaboom" in meta
    assert (run.run_dir / "events.jsonl").exists()


def test_experiment_config_snapshot_valid_toml(tmp_path):
    import tomllib

    script = tmp_path / "p.py"
    script.write_text("print('hi')\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=[], repeat=1)
    snapshot = tomllib.loads((result.experiment_dir / "config.toml").read_text())
    assert snapshot["trace"]["instrumentation"] == "hybrid"


def test_child_uses_same_interpreter(tmp_path):
    script = tmp_path / "interp.py"
    script.write_text(f"import sys\nassert sys.executable == {sys.executable!r}\n")
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=[], repeat=1)
    assert result.runs[0].exit_code == 0


def test_events_survive_hard_kill(tmp_path):
    """Crash-safety: a SIGKILLed run leaves a readable (possibly truncated)
    capture that analysis tolerates."""
    script = tmp_path / "killself.py"
    script.write_text(
        "import numpy as np, os, signal\n"
        "for i in range(50):\n"
        "    np.sum(np.arange(10.0))\n"
        "os.kill(os.getpid(), signal.SIGKILL)\n"
    )
    result = run_experiment(config=config_for(tmp_path), script=str(script),
                            script_args=[], target_specs=["numpy.sum"], repeat=1,
                            continue_on_error=True)
    assert result.runs[0].exit_code == -9
    from pytracer.trace.reader import load_run_calls

    calls, _truncated = load_run_calls(result.runs[0].run_dir)
    assert len(calls) >= 1  # flushed events are readable after SIGKILL
