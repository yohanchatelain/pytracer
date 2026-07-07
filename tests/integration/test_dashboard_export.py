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
