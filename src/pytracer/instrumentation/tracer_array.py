"""Tier T3 — tracer arrays (opt-in transparency mode).

A ``TracedArray`` is an ndarray subclass implementing ``__array_ufunc__``
and ``__array_function__``. Once a value is tainted (``pytracer.taint(x)``,
or automatically on traced-call outputs under ``--instrument taint``),
**every** NumPy operation on it dispatches through the protocol and is
recorded — including operator dispatch (``a + b``, ``a @ b``), ufunc
methods, and calls made from third-party Python code, regardless of how the
function was looked up. Protocol dispatch keys on the operand type, not on
module attributes, so aliasing cannot escape it.

Known hazards (why this tier is opt-in, plan §1.3):
- ``np.asarray`` (not ``asanyarray``) strips the subclass — taint dies at
  many C-extension entry points. T1 wrappers re-taint their outputs to
  re-seed it at known boundaries.
- Code doing exact ``type(x) is np.ndarray`` checks will see the subclass.
- Every elementwise operation emits events: overhead is high by design.
"""

from __future__ import annotations

import numpy as np

from pytracer.instrumentation.recorder import get_active_recorder


def _unwrap(value):
    if isinstance(value, TracedArray):
        return value.view(np.ndarray)
    if isinstance(value, tuple):
        return tuple(_unwrap(v) for v in value)
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def rewrap(value):
    """Wrap ndarray results (and tuples thereof) as TracedArray views."""
    if isinstance(value, TracedArray):
        return value
    if isinstance(value, np.ndarray):
        return value.view(TracedArray)
    if isinstance(value, tuple):
        return tuple(rewrap(v) for v in value)
    return value


class TracedArray(np.ndarray):
    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        unwrapped_inputs = tuple(_unwrap(x) for x in inputs)
        unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
        bound = getattr(ufunc, method)

        recorder = get_active_recorder()
        if recorder is None or recorder.context.inside():
            result = bound(*unwrapped_inputs, **unwrapped_kwargs)
        else:
            result = recorder.record_call(
                module=getattr(ufunc, "__module__", None) or "numpy",
                qualname=ufunc.__name__,
                tier="t3",
                wrapped=lambda *_a, **_k: bound(*unwrapped_inputs, **unwrapped_kwargs),
                args=unwrapped_inputs,
                kwargs=unwrapped_kwargs,
                ufunc_method=method,
                inplace=unwrapped_kwargs.get("out") is not None,
                bind_with=None,  # ufuncs have no introspectable signature
            )
        return rewrap(result)

    def __array_function__(self, func, types, args, kwargs):
        unwrapped_args = tuple(_unwrap(a) for a in args)
        unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}

        recorder = get_active_recorder()
        if recorder is None or recorder.context.inside():
            result = func(*unwrapped_args, **unwrapped_kwargs)
        else:
            result = recorder.record_call(
                module=getattr(func, "__module__", None) or "numpy",
                qualname=getattr(func, "__name__", "?"),
                tier="t3",
                wrapped=lambda *_a, **_k: func(*unwrapped_args, **unwrapped_kwargs),
                args=unwrapped_args,
                kwargs=unwrapped_kwargs,
                bind_with=func,
            )
        return rewrap(result)


def taint(value) -> TracedArray:
    """Mark an array-like so all subsequent NumPy operations on it are traced.

    Works everywhere; recording only happens inside a `pytracer run`.
    """
    return np.asarray(value).view(TracedArray)
