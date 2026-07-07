import pytest

from pytracer._errors import AlignmentError
from pytracer.analysis.aggregate import aggregate, sig_bits
from pytracer.analysis.align import align
from pytracer.trace.event import NumericSummary, SourceRef
from pytracer.trace.reader import CallRecord


def make_call(call_id, qualname="sum", occurrence=0, out_mean=6.0, in_mean=2.0, lineno=5):
    return CallRecord(
        call_id=call_id,
        module="numpy",
        qualname=qualname,
        tier="t1",
        ufunc_method=None,
        source=SourceRef(file="/x.py", lineno=lineno),
        occurrence=occurrence,
        inputs={"a": NumericSummary(dtype="float64", shape=(3,), size=3, mean=in_mean)},
        outputs={"Ret": NumericSummary(dtype="float64", shape=(), size=1, mean=out_mean)},
        first_event_id=call_id * 2,
    )


def test_sig_bits_exact():
    assert sig_bits([1.0, 1.0, 1.0]) == 53.0


def test_sig_bits_noisy():
    sig = sig_bits([1.0, 1.0 + 1e-6, 1.0 - 1e-6])
    assert 15 < sig < 25  # ~ -log2(8.2e-7)


def test_sig_bits_degenerate():
    assert sig_bits([0.0, 0.0]) == 53.0
    assert sig_bits([1.0]) is None
    assert sig_bits([float("nan"), 1.0]) is None  # single finite value


def test_align_callsite_matches_identical_runs():
    runs = [[make_call(0), make_call(1, occurrence=1)] for _ in range(3)]
    alignment = align(["r0", "r1", "r2"], runs, mode="callsite")
    assert len(alignment.groups) == 2
    assert all(g.complete for g in alignment.groups)


def test_align_reports_missing():
    full = [make_call(0), make_call(1, qualname="mean")]
    partial = [make_call(0)]
    alignment = align(["r0", "r1"], [full, partial], mode="callsite")
    summary = alignment.summary_dict()
    assert summary["matched_call_groups"] == 1
    assert summary["divergent_call_groups"] == 1
    (entry,) = summary["divergent_calls"]
    assert entry["function"] == "numpy.mean"
    assert entry["missing_in_runs"] == ["r1"]
    assert entry["divergence_score"] == 1.0


def test_align_strict_raises_on_divergence():
    full = [make_call(0), make_call(1, qualname="mean")]
    partial = [make_call(0)]
    with pytest.raises(AlignmentError, match="numpy.mean"):
        align(["r0", "r1"], [full, partial], mode="strict")


def test_aggregate_stable_runs():
    runs = [[make_call(0)] for _ in range(3)]
    alignment = align(["r0", "r1", "r2"], runs)
    result = aggregate(alignment)
    (row,) = result.functions
    assert row.function == "numpy.sum"
    assert row.min_output_sig_bits == 53.0
    assert row.divergence_score == 0.0


def test_aggregate_detects_amplification():
    # inputs identical across runs (53 bits), outputs vary (~17 bits):
    # the function destroys ~36 bits.
    runs = [
        [make_call(0, in_mean=2.0, out_mean=6.0)],
        [make_call(0, in_mean=2.0, out_mean=6.0 + 6e-5)],
        [make_call(0, in_mean=2.0, out_mean=6.0 - 6e-5)],
    ]
    alignment = align(["r0", "r1", "r2"], runs)
    result = aggregate(alignment)
    (row,) = result.functions
    assert row.min_output_sig_bits < 20
    assert row.max_amplification_bits > 30
    top = result.top_unstable()
    assert top[0].function == "numpy.sum"


def test_aggregate_nan_instability():
    calls = [make_call(0) for _ in range(2)]
    calls[1].outputs["Ret"].nan_count = 3
    alignment = align(["r0", "r1"], [[calls[0]], [calls[1]]])
    result = aggregate(alignment)
    assert result.functions[0].nan_instability


def test_top_unstable_ranks_amplifiers_first():
    stable = [make_call(0, qualname="stable", lineno=1) for _ in range(3)]
    noisy = [
        make_call(1, qualname="noisy", lineno=2, out_mean=1.0),
        make_call(1, qualname="noisy", lineno=2, out_mean=1.001),
        make_call(1, qualname="noisy", lineno=2, out_mean=0.999),
    ]
    runs = [[stable[i], noisy[i]] for i in range(3)]
    alignment = align(["r0", "r1", "r2"], runs)
    result = aggregate(alignment)
    top = result.top_unstable()
    assert top[0].function == "numpy.noisy"


def make_shaped_call(call_id, shape, occurrence=0, lineno=9):
    call = make_call(call_id, qualname="dot", occurrence=occurrence, lineno=lineno)
    call.inputs = {
        "a": NumericSummary(dtype="float64", shape=shape, size=1, mean=1.0)
    }
    return call


def test_fuzzy_alignment_localizes_insertion():
    """Run B has one extra call (different shape) inserted at the same
    callsite. Callsite mode misaligns everything after the insertion;
    fuzzy matches the common subsequence and reports one extra call."""
    shapes_a = [(2,), (3,), (4,)]
    shapes_b = [(2,), (9, 9), (3,), (4,)]  # (9, 9) inserted
    run_a = [make_shaped_call(i, s, occurrence=i) for i, s in enumerate(shapes_a)]
    run_b = [make_shaped_call(i, s, occurrence=i) for i, s in enumerate(shapes_b)]

    # callsite mode: occurrences 1 and 2 pair mismatched shapes silently
    cs = align(["A", "B"], [run_a, run_b], mode="callsite")
    mismatched = [
        g for g in cs.matched
        if g.calls[0].inputs["a"].shape != g.calls[1].inputs["a"].shape
    ]
    assert mismatched  # the documented cascade

    # fuzzy mode: all three common calls pair correctly, one extra reported
    fz = align(["A", "B"], [run_a, run_b], mode="fuzzy")
    complete = fz.matched
    assert len(complete) == 3
    for g in complete:
        assert g.calls[0].inputs["a"].shape == g.calls[1].inputs["a"].shape
    (extra,) = fz.divergent
    assert extra.calls[0] is None  # present only in run B
    assert extra.calls[1].inputs["a"].shape == (9, 9)


def test_fuzzy_alignment_identical_runs():
    runs = [[make_call(0), make_call(1, occurrence=1)] for _ in range(3)]
    alignment = align(["r0", "r1", "r2"], runs, mode="fuzzy")
    assert len(alignment.groups) == 2
    assert all(g.complete for g in alignment.groups)
