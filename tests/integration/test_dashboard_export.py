"""Dashboard construction and Perfetto export against a real experiment."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROGRAMS = Path(__file__).parent.parent / "programs"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("dashexp")
    shutil.copy(PROGRAMS / "simple_numpy.py", workdir)
    proc = subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", "run", "simple_numpy.py",
         "--repeat", "2", "--plugins", "--target", "numpy.sum",
         "--target", "numpy.linalg.norm"],
        cwd=workdir, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    root = workdir / ".pytracer" / "runs"
    (exp,) = [
        p for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    ]
    return exp


def test_perfetto_export(experiment):
    from pytracer.report.perfetto import export_perfetto

    out = export_perfetto(experiment)
    assert out.is_file()
    payload = json.loads(out.read_text())
    events = payload["traceEvents"]
    spans = [e for e in events if e.get("ph") == "X"]
    assert len(spans) >= 4  # 2 calls x 2 runs
    names = {e["name"] for e in spans}
    assert "numpy.sum" in names
    pids = {e["pid"] for e in spans}
    assert pids == {0, 1}
    assert all(e["dur"] > 0 for e in spans)
    # process rows named after runs
    metas = [e for e in events if e.get("ph") == "M"]
    assert {m["args"]["name"] for m in metas} == {"run-000", "run-001"}


def test_perfetto_cli(experiment, tmp_path):
    out = tmp_path / "trace.json"
    proc = subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", "export", str(experiment),
         "-o", str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()


@pytest.mark.skipif(importlib.util.find_spec("dash") is None, reason="dash not installed")
def test_dashboard_builds(experiment):
    from pytracer.dashboard.app import build_app

    app = build_app(experiment)
    assert app.layout is not None
    rendered = str(app.layout)
    assert "numpy.sum" in rendered
    # all five tabs present
    for tab in ("tab-overview", "tab-explorer", "tab-gantt",
                "tab-coverage", "tab-runs"):
        assert tab in rendered


def test_dashboard_data_layer(experiment):
    from pytracer.dashboard.data import ExperimentData

    data = ExperimentData(experiment)
    assert data.run_ids == ["run-000", "run-001"]
    assert data.timeline_rows, "timeline should have at least one row"
    row = data.timeline_rows[0]
    assert {"gidx", "function", "arg", "phase", "x", "sig_proxy",
            "mean", "has_arrays"} <= set(row)
    # per-run drill-down statistics
    detail = data.group_detail(row["gidx"], row["phase"], row["arg"])
    assert len(detail) == 2
    assert any(r.get("mean") is not None for r in detail)
    # call spans for the gantt
    spans, total = data.run_spans("run-000")
    assert total >= 2 and spans
    assert all(s["dur_us"] > 0 for s in spans)
    # timeline filters by function and phase
    fn = row["function"]
    only_inputs = data.timeline_for([fn], ["input"])
    assert only_inputs and all(r["phase"] == "input" for r in only_inputs)


@pytest.mark.skipif(importlib.util.find_spec("dash") is None, reason="dash not installed")
def test_dashboard_figures(experiment):
    from pytracer.dashboard import figures
    from pytracer.dashboard.data import ExperimentData

    data = ExperimentData(experiment)
    fig = figures.timeline_figure(
        data.timeline_for(data.functions, ["input", "output"]),
        "sig_proxy", "linear", data.functions)
    assert fig.data, "timeline should carry at least one trace"
    fig = figures.amplification_figure(data.report.get("top_unstable", []))
    assert fig is not None
    spans, total = data.run_spans("run-000")
    fig = figures.gantt_figure(spans, total, "run-000")
    assert fig.data


def test_call_graph(experiment):
    from pytracer.dashboard.data import ExperimentData

    data = ExperimentData(experiment)
    graph = data.call_graph()
    assert graph["nodes"], "traced functions should appear as nodes"
    assert "numpy.sum" in graph["nodes"]
    node = graph["nodes"]["numpy.sum"]
    assert node["calls"] >= 1
    # every edge endpoint is a known node (or the synthetic root)
    known = set(graph["nodes"]) | {graph["root"]}
    assert all(a in known and b in known for a, b in graph["edges"])
    # 2 runs -> cross-run output significance is measurable somewhere
    assert any(n["min_sig"] is not None for n in graph["nodes"].values())


@pytest.mark.skipif(importlib.util.find_spec("dash") is None, reason="dash not installed")
def test_callgraph_figure(experiment):
    from pytracer.dashboard import figures, theme
    from pytracer.dashboard.data import ExperimentData

    data = ExperimentData(experiment)
    fig = figures.callgraph_figure(data.call_graph())
    assert fig.layout.annotations, "edges should render as arrow annotations"
    # severity ramp endpoints
    assert theme.sig_to_color(0.0) == "rgb(208,59,59)"
    assert theme.sig_to_color(53.0) == "rgb(12,163,12)"
    assert theme.sig_to_color(None) == theme.UNKNOWN_GRAY


def test_elementwise_sig_array():
    import numpy as np

    from pytracer.dashboard.data import as_matrix, elementwise_sig_array

    stack = np.stack([np.array([1.0, 2.0, np.nan]),
                      np.array([1.0, 2.0 + 1e-12, np.nan])])
    sig = elementwise_sig_array(stack)
    assert sig.shape == (3,)
    assert sig[0] == 53.0  # identical -> capped
    assert 0 < sig[1] < 53.0  # perturbed
    assert np.isnan(sig[2])  # undefined
    assert as_matrix(np.zeros(4)).shape == (1, 4)
    assert as_matrix(np.zeros((2, 3, 4))).shape == (2, 12)


def test_dashboard_without_dash_errors_cleanly(experiment, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_dash(name, *args, **kwargs):
        if name == "dash":
            raise ImportError("no dash")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_dash)
    from pytracer._errors import PytracerError
    from pytracer.dashboard.app import build_app

    with pytest.raises(PytracerError, match="gui"):
        build_app(experiment)


@pytest.mark.skipif(importlib.util.find_spec("dash") is None, reason="dash not installed")
def test_dashboard_compare_mode(experiment):
    from pytracer.dashboard import figures
    from pytracer.dashboard.app import build_app
    from pytracer.dashboard.data import ExperimentData

    app = build_app(experiment, compare_dir=experiment)
    rendered = str(app.layout)
    assert "tab-diff" in rendered
    assert "Diff (A/B)" in rendered

    data = ExperimentData(experiment)
    diff_rows = data.diff_with(data)
    assert diff_rows
    assert all(r["status"] == "stable" for r in diff_rows)

    fig = figures.diff_waterfall_figure(diff_rows)
    assert fig is not None


def test_matrix_condition_summary(experiment):
    import numpy as np

    from pytracer.dashboard.data import ExperimentData

    data = ExperimentData(experiment)
    # Test condition number computation with mock 2D matrices stack
    hilbert = np.array([[1.0, 1 / 2, 1 / 3], [1 / 2, 1 / 3, 1 / 4], [1 / 3, 1 / 4, 1 / 5]])
    stack = np.stack([hilbert, hilbert * 1.0001])
    data._element_cache[(0, "input", "A")] = (np.array([53.0]), stack)
    summary = data.matrix_condition_summary(0, "input", "A")
    assert summary is not None
    assert summary["cond_median"] > 100.0
    assert summary["log10_cond"] > 2.0


@pytest.mark.skipif(importlib.util.find_spec("plotly") is None, reason="plotly not installed")
def test_theme_templates():
    from pytracer.dashboard import theme

    light = theme.make_template(dark=False)
    dark = theme.make_template(dark=True)
    assert light.layout.paper_bgcolor == theme.SURFACE
    assert dark.layout.paper_bgcolor == theme.DARK_SURFACE
    assert dark.layout.font.color == theme.DARK_INK


