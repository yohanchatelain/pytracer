"""Direct tests for report rendering and run metadata."""

from pytracer.report.render import (
    render_html,
    render_json,
    render_markdown,
    terminal_summary,
    write_reports,
)
from pytracer.trace.metadata import (
    RunMetadata,
    collect_run_metadata,
    filtered_environment,
    read_metadata,
    write_metadata,
)


def sample_data(sig_basis="summary"):
    return {
        "experiment": {"script": "/tmp/prog.py", "instrumentation": "hybrid"},
        "alignment": {
            "runs": 3,
            "alignment_mode": "callsite",
            "total_call_groups": 5,
            "matched_call_groups": 4,
            "divergent_call_groups": 1,
            "truncated_runs": ["run-002"],
            "divergent_calls": [
                {"function": "numpy.mean", "divergence_score": 0.2,
                 "missing_in_runs": ["run-001"]},
            ],
        },
        "coverage": {
            "calls_per_tier": {"t1": 10},
            "monitor_available": True,
            "untraced_numerical_callables": [{"function": "numpy.sum", "calls": 7}],
            "native_kernels": {"scipy_cblas_dgemm64_": {"calls": 2, "volume": 1000}},
            "notes": ["a coverage note"],
        },
        "functions": [
            {"function": "numpy.linalg.solve", "sig_basis": sig_basis,
             "min_output_sig_bits": 12.3, "max_amplification_bits": 20.0,
             "divergence_score": 0.0, "nan_instability": True,
             "inf_instability": False},
        ],
        "arguments": [],
        "top_unstable": [
            {"function": "numpy.linalg.solve", "sig_basis": sig_basis,
             "min_output_sig_bits": 12.3, "max_amplification_bits": 20.0,
             "divergence_score": 0.0, "nan_instability": True,
             "inf_instability": False},
        ],
        "runs": [{"python_version": "3.13.0", "platform": "Linux",
                  "packages": {"numpy": "2.5"}, "environment": {"OMP_NUM_THREADS": "1"}}],
    }


def test_markdown_contains_all_sections():
    md = render_markdown(sample_data())
    for expected in (
        "# Pytracer report", "numpy.linalg.solve", "12.3", "Truncated runs",
        "run-002", "numpy.mean", "Untraced numerical callables", "numpy.sum",
        "Native BLAS/LAPACK kernels", "scipy_cblas_dgemm64_", "a coverage note",
        "sig(mean)",  # summary-basis note
    ):
        assert expected in md, f"missing {expected!r}"


def test_markdown_element_basis_note():
    md = render_markdown(sample_data(sig_basis="element"))
    assert "element-wise significant digits" in md
    assert "| element " in md


def test_html_escapes_and_wraps():
    data = sample_data()
    data["experiment"]["script"] = "<script>alert(1)</script>"
    html = render_html(data)
    assert "<script>alert(1)</script>" not in html  # autoescaped
    assert "<!doctype html>" in html


def test_json_roundtrip():
    import json

    assert json.loads(render_json(sample_data()))["alignment"]["runs"] == 3


def test_terminal_summary_lists_top():
    text = terminal_summary(sample_data())
    assert "Pytracer run complete" in text
    assert "numpy.linalg.solve" in text


def test_write_reports_respects_formats(tmp_path):
    written = write_reports(tmp_path, sample_data(), ["markdown", "json"])
    names = {p.name for p in written}
    assert names == {"report.md", "report.json"}
    assert not (tmp_path / "report" / "report.html").exists()


def test_empty_data_renders():
    md = render_markdown({})
    assert "No traced calls" in md
    assert "Pytracer run complete" in terminal_summary({})


# --- metadata ----------------------------------------------------------------


def test_environment_allowlist_blocks_secrets():
    env = {
        "AWS_SECRET_ACCESS_KEY": "hunter2",
        "GITHUB_TOKEN": "ghp_x",
        "HOME": "/home/u",
        "OMP_NUM_THREADS": "4",
        "VFC_BACKENDS": "libinterflop_mca.so",
        "LD_PRELOAD": "/x.so",
        "PATH": "/usr/bin",
        "LC_ALL": "C",
    }
    filtered = filtered_environment(env)
    assert "AWS_SECRET_ACCESS_KEY" not in filtered
    assert "GITHUB_TOKEN" not in filtered
    assert "HOME" not in filtered
    assert filtered["OMP_NUM_THREADS"] == "4"
    assert filtered["VFC_BACKENDS"] == "libinterflop_mca.so"
    assert "LD_PRELOAD" in filtered and "PATH" in filtered and "LC_ALL" in filtered


def test_collect_and_roundtrip_metadata(tmp_path):
    meta = collect_run_metadata("exp-1", "run-000", ["prog.py", "--x"])
    assert isinstance(meta, RunMetadata)
    assert meta.schema_version == "2.0.0"
    assert meta.run_id == "run-000"
    assert "numpy" in meta.packages
    assert "AWS_SECRET_ACCESS_KEY" not in meta.environment

    path = tmp_path / "metadata.json"
    write_metadata(path, meta)
    loaded = read_metadata(path)
    assert loaded["experiment_id"] == "exp-1"
    assert loaded["command"] == ["prog.py", "--x"]
