"""Tier T1 — boundary patching of Python-level functions and methods.

Targets are dotted paths (``numpy.linalg.solve``,
``sklearn.decomposition.PCA.fit``) or globs on the final component
(``numpy.linalg.*``). Ufunc targets are routed to the T2 proxy.

Unpatching restores the exact previous state, including the case where a
method was inherited: patching placed the wrapper in the subclass dict, so
unpatching deletes it rather than assigning the base method onto the child.
"""

from __future__ import annotations

import fnmatch
import importlib
import inspect
from dataclasses import dataclass, field

import wrapt

from pytracer.instrumentation.recorder import Recorder
from pytracer.instrumentation.ufunc import TracedUfunc


@dataclass(slots=True)
class ResolvedTarget:
    spec: str
    module: str  # module name recorded in events
    qualname: str  # function/method name recorded in events
    parent: object  # object owning the attribute (module or class)
    attr: str
    original: object
    kind: str  # "function" | "method" | "ufunc"
    owned: bool  # attr was in vars(parent) before patching


@dataclass(slots=True)
class ResolutionReport:
    resolved: list[ResolvedTarget] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_ufunc(obj: object) -> bool:
    return type(obj).__name__ == "ufunc"


def _import_prefix(parts: list[str]) -> tuple[object | None, int]:
    """Import the longest importable dotted prefix; return (module, n_parts_used)."""
    module = None
    used = 0
    for i in range(len(parts), 0, -1):
        name = ".".join(parts[:i])
        try:
            module = importlib.import_module(name)
            used = i
            break
        except ImportError:
            continue
    return module, used


def _classify(obj: object) -> str | None:
    if _is_ufunc(obj):
        return "ufunc"
    if inspect.isroutine(obj):
        return "function"
    if callable(obj) and not inspect.isclass(obj) and not inspect.ismodule(obj):
        return "function"
    return None


def resolve_targets(specs: list[str]) -> ResolutionReport:
    report = ResolutionReport()
    seen: set[tuple[int, str]] = set()
    for spec in specs:
        try:
            _resolve_one(spec, report, seen)
        except Exception as e:
            report.errors.append(f"{spec}: {type(e).__name__}: {e}")
    return report


def _resolve_one(spec: str, report: ResolutionReport, seen: set[tuple[int, str]]) -> None:
    parts = spec.split(".")
    if "*" in spec:
        pattern = parts[-1]
        if any("*" in p for p in parts[:-1]):
            report.errors.append(f"{spec}: wildcards are only supported in the last component")
            return
        module, used = _import_prefix(parts[:-1])
        if module is None or used != len(parts) - 1:
            report.errors.append(f"{spec}: cannot import module {'.'.join(parts[:-1])!r}")
            return
        matches = 0
        for name in sorted(vars(module)):
            if name.startswith("_") or not fnmatch.fnmatch(name, pattern):
                continue
            obj = vars(module)[name]
            if _classify(obj) is not None:
                _add_target(f"{module.__name__}.{name}", module, name, obj, report, seen)
                matches += 1
        if matches == 0:
            report.errors.append(f"{spec}: no matching callables in {module.__name__}")
        return

    module, used = _import_prefix(parts)
    if module is None:
        report.errors.append(f"{spec}: cannot import any prefix of {spec!r}")
        return
    remainder = parts[used:]
    if not remainder:
        report.errors.append(f"{spec}: is a module; use {spec}.* to trace its functions")
        return
    parent: object = module
    for i, name in enumerate(remainder):
        try:
            obj = getattr(parent, name)
        except AttributeError:
            path = ".".join(parts[: used + i])
            report.errors.append(f"{spec}: {path!r} has no attribute {name!r}")
            return
        if i < len(remainder) - 1:
            parent = obj
    _add_target(spec, parent, remainder[-1], obj, report, seen)


def _add_target(
    spec: str,
    parent: object,
    attr: str,
    obj: object,
    report: ResolutionReport,
    seen: set[tuple[int, str]],
) -> None:
    key = (id(parent), attr)
    if key in seen:
        return
    kind = _classify(obj)
    if kind is None:
        report.errors.append(f"{spec}: not a traceable callable ({type(obj).__name__})")
        return
    if inspect.isclass(parent):
        module = getattr(parent, "__module__", "") or ""
        qualname = f"{parent.__name__}.{attr}"
        kind = "method" if kind == "function" else kind
    else:
        module = getattr(parent, "__name__", "") or ""
        qualname = attr
    seen.add(key)
    report.resolved.append(
        ResolvedTarget(
            spec=spec,
            module=module,
            qualname=qualname,
            parent=parent,
            attr=attr,
            original=obj,
            kind=kind,
            owned=attr in vars(parent),
        )
    )


class Patcher:
    def __init__(self, recorder: Recorder):
        self.recorder = recorder
        self._applied: list[ResolvedTarget] = []

    @property
    def applied(self) -> list[ResolvedTarget]:
        return list(self._applied)

    def patch(self, targets: list[ResolvedTarget]) -> None:
        for target in targets:
            if any(t.parent is target.parent and t.attr == target.attr for t in self._applied):
                continue  # idempotent
            wrapper = self._make_wrapper(target)
            setattr(target.parent, target.attr, wrapper)
            self._applied.append(target)

    def unpatch(self) -> None:
        for target in reversed(self._applied):
            try:
                if target.owned:
                    setattr(target.parent, target.attr, target.original)
                else:
                    delattr(target.parent, target.attr)
            except (AttributeError, TypeError):
                pass
        self._applied.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.unpatch()

    def _make_wrapper(self, target: ResolvedTarget):
        if target.kind == "ufunc":
            return TracedUfunc(target.original, self.recorder, target.module, target.qualname)
        recorder = self.recorder
        module, qualname = target.module, target.qualname

        def _traced(wrapped, instance, args, kwargs):
            return recorder.record_call(
                module=module,
                qualname=qualname,
                tier="t1",
                wrapped=wrapped,
                args=args,
                kwargs=kwargs,
            )

        return wrapt.FunctionWrapper(target.original, _traced)
