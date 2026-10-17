"""Tier T2 — ufunc interception.

A ``TracedUfunc`` is a wrapt.ObjectProxy around a real ufunc, so
``isinstance(numpy.add, numpy.ufunc)`` stays True and all ufunc attributes
(nin, nout, types, identity, ...) are forwarded. ``__call__`` and the ufunc
methods (reduce, accumulate, reduceat, outer, at) each emit events tagged
with the method name — a ``reduce`` is numerically a different operation
than an elementwise call.

Declared blind spot (see the plan, §1.2): operator dispatch (``a + b``)
goes through ndarray C type slots and never reads the module attribute; it
is not observable at this tier.
"""

from __future__ import annotations

import wrapt

from pytracer.instrumentation.recorder import Recorder


class TracedUfunc(wrapt.ObjectProxy):
    def __init__(self, wrapped, recorder: Recorder, module: str, qualname: str):
        super().__init__(wrapped)
        self._self_recorder = recorder
        self._self_module = module
        self._self_qualname = qualname

    def _self_record(self, method: str, bound, args, kwargs, inplace: bool = False):
        return self._self_recorder.record_call(
            module=self._self_module,
            qualname=self._self_qualname,
            tier="t2",
            wrapped=bound,
            args=args,
            kwargs=kwargs,
            ufunc_method=method,
            inplace=inplace,
        )

    @staticmethod
    def _has_out(val) -> bool:
        if val is None:
            return False
        if isinstance(val, tuple):
            return any(v is not None for v in val)
        return True

    def __call__(self, *args, **kwargs):
        nin = getattr(self.__wrapped__, "nin", 1)
        has_pos_out = len(args) > nin and any(self._has_out(a) for a in args[nin:])
        has_kw_out = self._has_out(kwargs.get("out"))
        inplace = bool(has_pos_out or has_kw_out)
        return self._self_record("__call__", self.__wrapped__, args, kwargs, inplace=inplace)

    def reduce(self, *args, **kwargs):
        inplace = self._has_out(kwargs.get("out")) or (
            len(args) > 3 and self._has_out(args[3])
        )
        return self._self_record("reduce", self.__wrapped__.reduce, args, kwargs, inplace=inplace)

    def reduceat(self, *args, **kwargs):
        inplace = self._has_out(kwargs.get("out")) or (
            len(args) > 4 and self._has_out(args[4])
        )
        return self._self_record(
            "reduceat", self.__wrapped__.reduceat, args, kwargs, inplace=inplace
        )

    def accumulate(self, *args, **kwargs):
        inplace = self._has_out(kwargs.get("out")) or (
            len(args) > 3 and self._has_out(args[3])
        )
        return self._self_record(
            "accumulate", self.__wrapped__.accumulate, args, kwargs, inplace=inplace
        )

    def outer(self, *args, **kwargs):
        inplace = self._has_out(kwargs.get("out"))
        return self._self_record("outer", self.__wrapped__.outer, args, kwargs, inplace=inplace)

    def at(self, *args, **kwargs):
        return self._self_record("at", self.__wrapped__.at, args, kwargs, inplace=True)
