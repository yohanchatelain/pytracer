"""Run metadata with allowlist-only environment capture.

The raw process environment is never stored: trace directories are meant to
be shared, and secrets must not leak into them.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import msgspec

from pytracer.trace.event import SCHEMA_VERSION

ENV_ALLOWLIST_EXACT = {"PATH", "LANG", "LD_PRELOAD", "PYTHONHASHSEED", "PYTHONPATH"}
ENV_ALLOWLIST_PREFIXES = ("OMP_", "OPENBLAS_", "MKL_", "BLIS_", "VFC_", "VERROU_", "LC_")

_PACKAGES_OF_INTEREST = ("numpy", "scipy", "scikit-learn", "pytracer")


class RunMetadata(msgspec.Struct):
    schema_version: str
    experiment_id: str
    run_id: str
    created_at: str
    command: list[str]
    python_version: str
    pytracer_version: str
    platform: str
    executable: str
    packages: dict[str, str]
    environment: dict[str, str]
    exit_code: int | None = None
    error: str | None = None
    unresolved_targets: list[str] = []
    notes: list[str] = []


def filtered_environment(environ: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    out: dict[str, str] = {}
    for key, value in env.items():
        if key in ENV_ALLOWLIST_EXACT or key.startswith(ENV_ALLOWLIST_PREFIXES):
            out[key] = value
    return out


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGES_OF_INTEREST:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            continue
    return versions


def collect_run_metadata(experiment_id: str, run_id: str, command: list[str]) -> RunMetadata:
    from pytracer import __version__

    return RunMetadata(
        schema_version=SCHEMA_VERSION,
        experiment_id=experiment_id,
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(),
        command=list(command),
        python_version=sys.version.split()[0],
        pytracer_version=__version__,
        platform=platform.platform(),
        executable=sys.executable,
        packages=package_versions(),
        environment=filtered_environment(),
    )


def write_metadata(path: str | Path, meta: RunMetadata) -> None:
    Path(path).write_bytes(msgspec.json.format(msgspec.json.encode(meta), indent=2))


def read_metadata(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_bytes())
