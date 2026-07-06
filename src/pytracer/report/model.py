"""Assemble report data from an experiment's analysis directory."""

from __future__ import annotations

import json
from pathlib import Path

from pytracer._errors import PytracerError
from pytracer.trace.event import SCHEMA_VERSION


def build_report_data(experiment_dir: str | Path) -> dict:
    experiment_dir = Path(experiment_dir)
    analysis = experiment_dir / "analysis"
    if not analysis.is_dir():
        raise PytracerError(
            f"{experiment_dir}: no analysis directory (run `pytracer analyze` first)"
        )

    def _load(name: str, default):
        path = analysis / name
        return json.loads(path.read_text()) if path.is_file() else default

    alignment = _load("alignment.json", {})
    functions = _load("function_summary.json", [])
    arguments = _load("argument_summary.json", [])
    top = _load("top_unstable.json", [])
    coverage = _load("coverage.json", {})

    experiment_meta = {}
    exp_path = experiment_dir / "experiment.json"
    if exp_path.is_file():
        experiment_meta = json.loads(exp_path.read_text())

    run_metas = []
    runs_dir = experiment_dir / "runs"
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            meta_path = run_dir / "metadata.json"
            if meta_path.is_file():
                run_metas.append(json.loads(meta_path.read_text()))

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": experiment_meta,
        "alignment": alignment,
        "coverage": coverage,
        "functions": functions,
        "arguments": arguments,
        "top_unstable": top,
        "runs": run_metas,
    }
