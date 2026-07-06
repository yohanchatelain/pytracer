"""Plugin interface: plugins declare default trace targets.

Plugins import their library lazily — pytracer must never constrain the
versions of the libraries it studies, nor require them to be installed.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TraceTarget:
    import_path: str
    kind: str = "function"  # "function" | "method" | "ufunc"
    tags: tuple[str, ...] = ()


@dataclass(slots=True)
class PytracerPlugin:
    name: str
    requires: str  # top-level distribution/module the plugin traces
    targets: list[TraceTarget] = field(default_factory=list)

    def available(self) -> bool:
        return importlib.util.find_spec(self.requires) is not None

    def target_specs(self) -> list[str]:
        return [t.import_path for t in self.targets]
