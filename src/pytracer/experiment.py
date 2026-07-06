"""Experiment orchestration: one experiment = N independent runs of a script.

Directory layout:

    <output_dir>/<experiment_id>/
      .pytracer-experiment          # ownership marker (clean only deletes marked dirs)
      config.toml                   # resolved config snapshot
      experiment.json               # experiment-level metadata
      runs/run-000/{metadata.json, events.jsonl, events.parquet, monitor.json}
      analysis/                     # written by pytracer analyze / run
      report/                       # written by pytracer report / run
    <output_dir>/latest -> <experiment_id>
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import tomli_w

from pytracer._errors import ExperimentError
from pytracer.config.schema import PytracerConfig

MARKER = ".pytracer-experiment"


@dataclass(slots=True)
class RunResult:
    run_id: str
    run_dir: Path
    exit_code: int


@dataclass(slots=True)
class ExperimentResult:
    experiment_id: str
    experiment_dir: Path
    runs: list[RunResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def failed_runs(self) -> list[RunResult]:
        return [r for r in self.runs if r.exit_code != 0]


def create_experiment_dir(output_dir: str | Path, config: PytracerConfig) -> tuple[str, Path]:
    experiment_id = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S.%f")[:-3] + "Z"
    experiment_dir = Path(output_dir) / experiment_id
    (experiment_dir / "runs").mkdir(parents=True)
    (experiment_dir / MARKER).touch()
    (experiment_dir / "config.toml").write_text(tomli_w.dumps(config.to_dict()))
    _update_latest(Path(output_dir), experiment_id)
    return experiment_id, experiment_dir


def _update_latest(output_dir: Path, experiment_id: str) -> None:
    latest = output_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(experiment_id)
    except OSError:
        pass  # symlinks may be unsupported; "latest" is a convenience only


def run_experiment(
    *,
    config: PytracerConfig,
    script: str,
    script_args: list[str],
    target_specs: list[str],
    repeat: int,
    continue_on_error: bool = False,
    env_overrides: dict[str, str] | None = None,
) -> ExperimentResult:
    script_path = Path(script)
    if not script_path.is_file():
        raise ExperimentError(f"script not found: {script}")
    if repeat < 1:
        raise ExperimentError(f"--repeat must be >= 1, got {repeat}")

    experiment_id, experiment_dir = create_experiment_dir(config.storage.output_dir, config)
    result = ExperimentResult(experiment_id=experiment_id, experiment_dir=experiment_dir)

    (experiment_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "script": str(script_path.resolve()),
                "script_args": script_args,
                "repeat": repeat,
                "targets": target_specs,
                "instrumentation": config.trace.instrumentation,
            },
            indent=2,
        )
    )

    import os

    for k in range(repeat):
        run_id = f"run-{k:03d}"
        run_dir = experiment_dir / "runs" / run_id
        run_dir.mkdir(parents=True)
        spec = {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "run_dir": str(run_dir),
            "script": str(script_path.resolve()),
            "script_args": script_args,
            "targets": target_specs,
            "instrumentation": config.trace.instrumentation,
            "mode": config.trace.mode,
            "capture_backtrace": config.trace.capture_backtrace,
        }
        spec_path = run_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2))

        env = dict(os.environ)
        env["PYTRACER_RUN_ID"] = run_id
        if env_overrides:
            env.update(env_overrides)

        proc = subprocess.run(
            [sys.executable, "-m", "pytracer._bootstrap", str(spec_path)],
            env=env,
            cwd=str(script_path.resolve().parent),
        )
        result.runs.append(RunResult(run_id=run_id, run_dir=run_dir, exit_code=proc.returncode))
        if proc.returncode != 0 and not continue_on_error:
            result.warnings.append(
                f"{run_id} exited with code {proc.returncode}; stopping "
                f"(use --continue-on-error to keep going)"
            )
            break

    return result


def find_experiments(output_dir: str | Path) -> list[Path]:
    root = Path(output_dir)
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / MARKER).is_file()
    )
