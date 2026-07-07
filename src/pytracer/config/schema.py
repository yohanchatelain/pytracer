"""Configuration schema.

Only options that are actually implemented appear here; unknown keys in
pytracer.toml are reported as errors rather than silently absorbed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

from pytracer._errors import ConfigError

Instrumentation = Literal["hybrid", "patch", "monitor", "taint"]
TraceMode = Literal["summary", "metadata"]
AlignmentMode = Literal["strict", "callsite", "fuzzy"]
ReportFormat = Literal["markdown", "html", "json"]

_VALID_INSTRUMENTATION = ("hybrid", "patch", "monitor", "taint")
_VALID_MODES = ("summary", "metadata")
_VALID_ALIGNMENT = ("strict", "callsite", "fuzzy")
_VALID_FORMATS = ("markdown", "html", "json")
_VALID_STORE_ARRAYS = ("auto", "always", "never")


@dataclass(slots=True)
class TraceConfig:
    plugins: list[str] = field(default_factory=lambda: ["numpy"])
    targets: list[str] = field(default_factory=list)
    instrumentation: str = "hybrid"
    mode: str = "summary"
    capture_backtrace: bool = True
    store_arrays: str = "auto"
    array_store_threshold: int = 100_000


@dataclass(slots=True)
class StorageConfig:
    output_dir: str = ".pytracer/runs"


@dataclass(slots=True)
class AnalysisConfig:
    alignment: str = "callsite"


@dataclass(slots=True)
class ReportConfig:
    formats: list[str] = field(default_factory=lambda: ["markdown", "html", "json"])


@dataclass(slots=True)
class PytracerConfig:
    trace: TraceConfig = field(default_factory=TraceConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    report: ReportConfig = field(default_factory=ReportConfig)

    def validate(self) -> None:
        if self.trace.instrumentation not in _VALID_INSTRUMENTATION:
            raise ConfigError(
                f"trace.instrumentation must be one of {_VALID_INSTRUMENTATION}, "
                f"got {self.trace.instrumentation!r}"
            )
        if self.trace.store_arrays not in _VALID_STORE_ARRAYS:
            raise ConfigError(
                f"trace.store_arrays must be one of {_VALID_STORE_ARRAYS}, "
                f"got {self.trace.store_arrays!r}"
            )
        if not isinstance(self.trace.array_store_threshold, int) or (
            self.trace.array_store_threshold < 0
        ):
            raise ConfigError("trace.array_store_threshold must be a non-negative integer")
        if self.trace.mode not in _VALID_MODES:
            raise ConfigError(
                f"trace.mode must be one of {_VALID_MODES}, got {self.trace.mode!r}"
            )
        if self.analysis.alignment not in _VALID_ALIGNMENT:
            raise ConfigError(
                f"analysis.alignment must be one of {_VALID_ALIGNMENT}, "
                f"got {self.analysis.alignment!r}"
            )
        for fmt in self.report.formats:
            if fmt not in _VALID_FORMATS:
                raise ConfigError(
                    f"report.formats entries must be in {_VALID_FORMATS}, got {fmt!r}"
                )
        for name, value in (
            ("trace.plugins", self.trace.plugins),
            ("trace.targets", self.trace.targets),
        ):
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ConfigError(f"{name} must be a list of strings")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_SECTIONS = {
    "trace": TraceConfig,
    "storage": StorageConfig,
    "analysis": AnalysisConfig,
    "report": ReportConfig,
}


def config_from_dict(data: dict[str, Any], source: str = "<dict>") -> PytracerConfig:
    unknown_sections = set(data) - set(_SECTIONS)
    if unknown_sections:
        raise ConfigError(
            f"{source}: unknown section(s) {sorted(unknown_sections)}; "
            f"valid sections are {sorted(_SECTIONS)}"
        )
    kwargs: dict[str, Any] = {}
    for section_name, section_cls in _SECTIONS.items():
        section_data = data.get(section_name, {})
        if not isinstance(section_data, dict):
            raise ConfigError(f"{source}: section [{section_name}] must be a table")
        valid_keys = {f.name for f in fields(section_cls)}
        unknown_keys = set(section_data) - valid_keys
        if unknown_keys:
            raise ConfigError(
                f"{source}: unknown key(s) {sorted(unknown_keys)} in [{section_name}]; "
                f"valid keys are {sorted(valid_keys)}"
            )
        kwargs[section_name] = section_cls(**section_data)
    config = PytracerConfig(**kwargs)
    config.validate()
    return config
