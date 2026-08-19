import numpy as np

from pytracer.trace.summary import array_fingerprint, summarize_value


def test_scalar_int():
    s = summarize_value(3)
    assert s is not None
    assert s.size == 1 and s.shape == ()
    assert s.mean == 3.0 and s.std == 0.0


def test_scalar_float_and_bool():
    assert summarize_value(2.5).mean == 2.5
    assert summarize_value(True).mean == 1.0


def test_complex_uses_abs():
    s = summarize_value(3 + 4j)
    assert s.mean == 5.0


def test_array_stats():
    s = summarize_value(np.array([1.0, 2.0, 3.0]))
    assert s.shape == (3,) and s.size == 3
    assert s.mean == 2.0 and s.min == 1.0 and s.max == 3.0
    assert s.fingerprint is not None


def test_nan_inf_counting():
    s = summarize_value(np.array([1.0, np.nan, np.inf, -np.inf, 0.0]))
    assert s.nan_count == 1 and s.inf_count == 2 and s.zero_count == 1
    # stats computed over finite values only
    assert s.mean == 0.5 and s.min == 0.0 and s.max == 1.0


def test_subnormal_counting():
    tiny = np.finfo(np.float64).tiny
    s = summarize_value(np.array([tiny / 2, 1.0]))
    assert s.subnormal_count == 1


def test_empty_array():
    s = summarize_value(np.array([], dtype=np.float64))
    assert s.size == 0 and s.mean is None


def test_non_numeric_returns_none():
    assert summarize_value("hello") is None
    assert summarize_value({"a": 1}) is None
    assert summarize_value(np.array(["a", "b"])) is None
    assert summarize_value(np.array([object()], dtype=object)) is None


def test_fingerprint_stable_and_shape_sensitive():
    a = np.arange(12, dtype=np.float64)
    assert array_fingerprint(a) == array_fingerprint(a.copy())
    assert array_fingerprint(a) != array_fingerprint(a.reshape(3, 4))
    assert array_fingerprint(a) != array_fingerprint(a + 1)


def test_fingerprint_large_contiguous_bounded():
    a = np.zeros(2_000_000, dtype=np.float64)  # 16 MB
    assert array_fingerprint(a, max_bytes=1_000_000) is not None


def test_fingerprint_large_noncontiguous_skipped():
    a = np.zeros((4000, 1000), dtype=np.float64)[:, ::2]  # non-contiguous, 16 MB
    assert array_fingerprint(a, max_bytes=1_000_000) is None


def test_summary_never_raises_on_weird_objects():
    class Weird:
        def __array__(self):
            raise RuntimeError("no")

    assert summarize_value(Weird()) is None
