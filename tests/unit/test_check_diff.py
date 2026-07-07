import json

import pytest

from pytracer._errors import ConfigError, PytracerError
from pytracer.analysis.check import Thresholds, check_experiment, load_thresholds_file
from pytracer.analysis.diff import diff_experiments, format_diff


def write_summary(tmp_path, rows):
    analysis = tmp_path / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    (analysis / "function_summary.json").write_text(json.dumps(rows))
    return tmp_path


def row(function, sig=53.0, divergence=0.0, nan=False, inf=False):
    return {
        "function": function,
        "min_output_sig_bits": sig,
        "divergence_score": divergence,
        "nan_instability": nan,
        "inf_instability": inf,
    }


def test_check_passes_when_stable(tmp_path):
    exp = write_summary(tmp_path, [row("numpy.sum")])
    violations = check_experiment(exp, Thresholds(min_sig_bits=20, max_divergence=0.01))
    assert violations == []


def test_check_flags_low_sig_and_divergence(tmp_path):
    exp = write_summary(
        tmp_path, [row("bad.fn", sig=5.0, divergence=0.5), row("ok.fn")]
    )
    violations = check_experiment(exp, Thresholds(min_sig_bits=20, max_divergence=0.01))
    assert len(violations) == 2
    assert all(v.function == "bad.fn" for v in violations)
    metrics = {v.metric for v in violations}
    assert metrics == {"min_output_sig_bits", "divergence_score"}


def test_check_nan_inf_gates(tmp_path):
    exp = write_summary(tmp_path, [row("nan.fn", nan=True), row("inf.fn", inf=True)])
    assert check_experiment(exp, Thresholds()) == []  # allowed by default
    violations = check_experiment(exp, Thresholds(allow_nan=False, allow_inf=False))
    assert {v.metric for v in violations} == {"nan_instability", "inf_instability"}


def test_check_per_function_override(tmp_path):
    exp = write_summary(tmp_path, [row("known.noisy", sig=8.0), row("other.fn", sig=8.0)])
    thresholds = Thresholds(
        min_sig_bits=20, per_function={"known.noisy": {"min_sig_bits": 5}}
    )
    violations = check_experiment(exp, thresholds)
    assert [v.function for v in violations] == ["other.fn"]


def test_check_missing_analysis_raises(tmp_path):
    with pytest.raises(PytracerError, match="analyze"):
        check_experiment(tmp_path, Thresholds(min_sig_bits=1))


def test_thresholds_file_roundtrip(tmp_path):
    path = tmp_path / "pytracer-thresholds.toml"
    path.write_text(
        "min_sig_bits = 20\nmax_divergence = 0.01\nallow_nan = false\n"
        '[function."numpy.linalg.solve"]\nmin_sig_bits = 10\n'
    )
    thresholds = load_thresholds_file(path)
    assert thresholds.min_sig_bits == 20
    assert not thresholds.allow_nan
    assert thresholds.for_function("numpy.linalg.solve")["min_sig_bits"] == 10
    assert thresholds.for_function("other")["min_sig_bits"] == 20


def test_thresholds_file_unknown_key(tmp_path):
    path = tmp_path / "t.toml"
    path.write_text("min_sig = 20\n")
    with pytest.raises(ConfigError, match="unknown key"):
        load_thresholds_file(path)


def test_diff_detects_regression_and_new_functions(tmp_path):
    a = write_summary(tmp_path / "a", [row("f.stable"), row("f.regressed", sig=40.0),
                                       row("f.gone")])
    b = write_summary(tmp_path / "b", [row("f.stable"), row("f.regressed", sig=10.0),
                                       row("f.new", sig=30.0)])
    result = diff_experiments(a, b)
    regressions = result.regressions(tolerance_bits=1.0)
    assert [r.function for r in regressions] == ["f.regressed"]
    assert result.only_in_a == ["f.gone"]
    assert result.only_in_b == ["f.new"]
    text = format_diff(result)
    assert "REGRESSION" in text and "f.gone" in text


def test_diff_tolerance(tmp_path):
    a = write_summary(tmp_path / "a", [row("f", sig=40.0)])
    b = write_summary(tmp_path / "b", [row("f", sig=39.5)])
    result = diff_experiments(a, b)
    assert result.regressions(tolerance_bits=1.0) == []
    assert len(result.regressions(tolerance_bits=0.1)) == 1
