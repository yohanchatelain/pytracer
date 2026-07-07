"""Analysis pipeline: align runs, aggregate metrics, account coverage."""

from __future__ import annotations

from pathlib import Path

from pytracer.analysis.aggregate import AggregationResult, aggregate, write_aggregation
from pytracer.analysis.align import (
    Alignment,
    align,
    load_experiment_calls,
    write_alignment,
)
from pytracer.analysis.coverage import build_coverage, write_coverage

__all__ = ["analyze_experiment", "Alignment", "AggregationResult"]


def analyze_experiment(
    experiment_dir: str | Path,
    alignment_mode: str = "callsite",
    target_specs: list[str] | None = None,
) -> tuple[Alignment, AggregationResult, dict]:
    """Full analysis pass over an experiment directory; writes analysis/*."""
    import json

    experiment_dir = Path(experiment_dir)
    if target_specs is None:
        exp_meta_path = experiment_dir / "experiment.json"
        target_specs = []
        if exp_meta_path.is_file():
            target_specs = json.loads(exp_meta_path.read_text()).get("targets", [])

    run_ids, calls_per_run, truncated = load_experiment_calls(experiment_dir)
    alignment = align(run_ids, calls_per_run, mode=alignment_mode, truncated_runs=truncated)
    write_alignment(experiment_dir, alignment)

    run_dirs = [experiment_dir / "runs" / run_id for run_id in run_ids]
    aggregation = aggregate(alignment, run_dirs=run_dirs)
    write_aggregation(experiment_dir, aggregation)

    coverage = build_coverage(experiment_dir, calls_per_run, target_specs)
    write_coverage(experiment_dir, coverage)
    return alignment, aggregation, coverage
