"""Interactive dashboard (`pip install pytracer[gui]`).

Reads a completed experiment — analysis aggregates are never recomputed;
call-level records are re-assembled in memory for drill-down. Five tabs:

- Overview:      KPI row, amplification & significance rankings, sortable
                 function/argument tables, control-flow divergence.
- Explorer:      per-invocation timeline (the pytracer 1 core view) with
                 metric/phase/scale controls; click any point for per-run
                 statistics, element-wise heatmaps + histogram, and the
                 calling source context.
- Call timeline: per-run call spans from capture timestamps (Gantt).
- Coverage:      calls per tier, native kernel census, untraced callables.
- Runs:          per-run metadata, captured environment, reproduce block.
"""

from __future__ import annotations

from pathlib import Path

from pytracer._errors import PytracerError


def _require_dash():
    try:
        import dash  # noqa: F401
    except ImportError as e:
        raise PytracerError(
            "the dashboard requires the gui extra: pip install 'pytracer[gui]'"
        ) from e


def build_app(experiment_dir: str | Path):
    _require_dash()
    from dash import Dash

    from pytracer.dashboard.callbacks import register_callbacks
    from pytracer.dashboard.data import ExperimentData
    from pytracer.dashboard.layout import build_layout

    data = ExperimentData(experiment_dir)
    app = Dash(
        __name__,
        title="Pytracer · Numerical Variability Profiler",
        assets_folder=str(Path(__file__).parent / "assets"),
        suppress_callback_exceptions=True,
    )
    app.layout = build_layout(data)
    register_callbacks(app, data)
    return app


def run_dashboard(experiment_dir: str | Path, host: str = "127.0.0.1",
                  port: int = 8050, debug: bool = False) -> None:
    app = build_app(experiment_dir)
    app.run(host=host, port=port, debug=debug)

