"""pytracer check — gate CI on numerical stability.

Thresholds come from CLI flags and/or a ``pytracer-thresholds.toml`` file:

    min_sig_bits = 20
    max_divergence = 0.01
    allow_nan = false
    allow_inf = false

    [function."numpy.linalg.solve"]
    min_sig_bits = 10          # per-function override

CLI flags override file values; per-function tables override both defaults.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pytracer._errors import ConfigError, PytracerError

THRESHOLDS_FILENAME = "pytracer-thresholds.toml"

_DEFAULT_KEYS = {"min_sig_bits", "max_divergence", "allow_nan", "allow_inf"}


@dataclass(slots=True)
class Thresholds:
    min_sig_bits: float | None = None
    max_divergence: float | None = None
    allow_nan: bool = True
    allow_inf: bool = True
    per_function: dict[str, dict] = field(default_factory=dict)

    def for_function(self, function: str) -> dict:
        limits = {
            "min_sig_bits": self.min_sig_bits,
            "max_divergence": self.max_divergence,
            "allow_nan": self.allow_nan,
            "allow_inf": self.allow_inf,
        }
        limits.update(self.per_function.get(function, {}))
        return limits


@dataclass(slots=True)
class Violation:
    function: str
    metric: str
    value: float | bool | None
    limit: float | bool | None

    def __str__(self) -> str:
        if self.metric in ("nan_instability", "inf_instability"):
            return f"{self.function}: {self.metric} detected (not allowed)"
        return (
            f"{self.function}: {self.metric} = {self.value} "
            f"violates limit {self.limit}"
        )


def load_thresholds_file(path: str | Path) -> Thresholds:
    path = Path(path)
    try:
        with open(path, "rb") as fo:
            data = tomllib.load(fo)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e

    unknown = set(data) - _DEFAULT_KEYS - {"function"}
    if unknown:
        raise ConfigError(
            f"{path}: unknown key(s) {sorted(unknown)}; "
            f"valid keys are {sorted(_DEFAULT_KEYS)} plus [function.\"name\"] tables"
        )
    per_function = {}
    for name, table in data.get("function", {}).items():
        bad = set(table) - _DEFAULT_KEYS
        if bad:
            raise ConfigError(f'{path}: unknown key(s) {sorted(bad)} in [function."{name}"]')
        per_function[name] = table
    return Thresholds(
        min_sig_bits=data.get("min_sig_bits"),
        max_divergence=data.get("max_divergence"),
        allow_nan=data.get("allow_nan", True),
        allow_inf=data.get("allow_inf", True),
        per_function=per_function,
    )


def load_function_summary(experiment_dir: str | Path) -> list[dict]:
    path = Path(experiment_dir) / "analysis" / "function_summary.json"
    if not path.is_file():
        raise PytracerError(
            f"{experiment_dir}: no analysis/function_summary.json "
            f"(run `pytracer analyze` first)"
        )
    return json.loads(path.read_text())


def check_experiment(experiment_dir: str | Path, thresholds: Thresholds) -> list[Violation]:
    violations: list[Violation] = []
    for row in load_function_summary(experiment_dir):
        function = row["function"]
        limits = thresholds.for_function(function)

        min_sig = limits.get("min_sig_bits")
        sig = row.get("min_output_sig_bits")
        if min_sig is not None and sig is not None and sig < min_sig:
            violations.append(Violation(function, "min_output_sig_bits", sig, min_sig))

        max_div = limits.get("max_divergence")
        div = row.get("divergence_score", 0.0)
        if max_div is not None and div > max_div:
            violations.append(Violation(function, "divergence_score", div, max_div))

        if not limits.get("allow_nan", True) and row.get("nan_instability"):
            violations.append(Violation(function, "nan_instability", True, False))
        if not limits.get("allow_inf", True) and row.get("inf_instability"):
            violations.append(Violation(function, "inf_instability", True, False))
    return violations
