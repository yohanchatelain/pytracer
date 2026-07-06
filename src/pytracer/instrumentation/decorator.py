"""Explicit user instrumentation: @pytracer.trace_function.

Traces the decorated function when a pytracer run is active; otherwise the
function runs untouched, so decorated code works outside `pytracer run`.
"""

from __future__ import annotations

import wrapt

from pytracer.instrumentation.recorder import get_active_recorder


@wrapt.decorator
def trace_function(wrapped, instance, args, kwargs):
    recorder = get_active_recorder()
    if recorder is None:
        return wrapped(*args, **kwargs)
    module = getattr(wrapped, "__module__", "") or ""
    qualname = getattr(wrapped, "__qualname__", getattr(wrapped, "__name__", "?"))
    return recorder.record_call(
        module=module,
        qualname=qualname,
        tier="t1",
        wrapped=wrapped,
        args=args,
        kwargs=kwargs,
    )
