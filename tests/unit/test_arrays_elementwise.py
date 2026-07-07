import numpy as np

from pytracer.analysis.elementwise import elementwise_sig, stack_arrays
from pytracer.storage.arrays import ArrayStore, load_array, make_array_store


def test_store_roundtrip(tmp_path):
    store = ArrayStore(tmp_path, mode="always")
    a = np.arange(6.0).reshape(2, 3)
    ref = store.maybe_store(1, "input", "x", a)
    assert ref is not None and ref.startswith("arrays/")
    loaded = load_array(tmp_path, ref)
    np.testing.assert_array_equal(loaded, a)


def test_store_eligibility():
    store = ArrayStore("/nonexistent-never-written", mode="auto", threshold=10)
    assert not store._eligible("hello")
    assert not store._eligible(np.array([], dtype=np.float64))
    assert not store._eligible(np.array([object()], dtype=object))
    assert not store._eligible(np.zeros(100))  # over threshold in auto mode
    assert store._eligible(np.zeros(5))


def test_store_always_ignores_threshold(tmp_path):
    store = ArrayStore(tmp_path, mode="always", threshold=1)
    assert store.maybe_store(1, "input", "x", np.zeros(100)) is not None


def test_store_arg_name_sanitized(tmp_path):
    store = ArrayStore(tmp_path, mode="always")
    ref = store.maybe_store(1, "input", "weird/arg name*", np.ones(2))
    assert ref is not None
    assert load_array(tmp_path, ref) is not None


def test_make_array_store_never():
    assert make_array_store("/tmp", "never") is None


def test_load_missing_returns_none(tmp_path):
    assert load_array(tmp_path, "arrays/missing.npy") is None


# --- element-wise significance ------------------------------------------------


def test_elementwise_identical_runs_full_precision():
    stack = np.stack([np.arange(1.0, 5.0)] * 3)
    result = elementwise_sig(stack)
    assert result["min"] == 53.0 and result["median"] == 53.0


def test_elementwise_noisy_runs():
    rng = np.random.default_rng(42)
    base = np.full(1000, 100.0)
    stack = np.stack([base + rng.normal(0, 1e-6, 1000) for _ in range(5)])
    result = elementwise_sig(stack)
    assert 20 < result["min"] < 32
    assert result["median"] > result["min"] - 10


def test_elementwise_catches_permutation_summary_misses():
    """The reason element-wise sig exists: runs whose arrays are permutations
    of each other have IDENTICAL summary statistics (sig(mean) = 53) but
    near-zero element-wise significance."""
    rng = np.random.default_rng(0)
    values = rng.uniform(1.0, 2.0, 100)
    stack = np.stack([rng.permutation(values) for _ in range(4)])

    # The summary proxy is wildly optimistic: the means differ only by
    # summation-order rounding (~1 ulp), so sig(mean) reports >40 bits.
    means = stack.mean(axis=1)
    rel_spread = np.ptp(means) / abs(means.mean())
    proxy_sig = -np.log2(rel_spread) if rel_spread > 0 else 53.0
    assert proxy_sig > 40

    # Element-wise sees the near-total loss the proxy misses.
    result = elementwise_sig(stack)
    assert result["median"] < 8.0


def test_elementwise_zero_mean_and_exact():
    stack = np.array([[0.0, 1.0], [0.0, 1.0], [1e-8, 1.0]])
    result = elementwise_sig(stack)
    assert result["min"] == 0.0  # varying element with zero mean... sig 0
    # second element exact across runs
    assert result["n_elements"] == 2


def test_elementwise_scalar_stack():
    stack = np.array([6.0, 6.0 + 1e-6, 6.0 - 1e-6])
    result = elementwise_sig(stack)
    assert result is not None and 15 < result["min"] < 25


def test_elementwise_nan_elements_excluded():
    stack = np.array([[np.nan, 1.0], [np.nan, 1.0]])
    result = elementwise_sig(stack)
    assert result["n_elements"] == 1 and result["n_undefined"] == 1


def test_stack_arrays_shape_mismatch_none():
    assert stack_arrays([np.zeros(3), np.zeros(4)]) is None
    assert stack_arrays([np.zeros(3), None]) is None
    assert stack_arrays([np.zeros(3)]) is None


def test_stack_arrays_complex_uses_abs():
    stack = stack_arrays([np.array([3 + 4j]), np.array([3 + 4j])])
    assert stack is not None
    np.testing.assert_allclose(stack, [[5.0], [5.0]])
