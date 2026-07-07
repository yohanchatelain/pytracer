"""Configuration loading: CLI overrides > ./pytracer.toml > built-in defaults.

No environment variable is required. Loading is explicit — nothing in this
module runs at import time.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pytracer._errors import ConfigError
from pytracer.config.schema import PytracerConfig, config_from_dict

CONFIG_FILENAME = "pytracer.toml"

DEFAULT_TOML = """\
# Pytracer configuration. All keys are optional; these are the defaults.

[trace]
plugins = ["numpy"]
targets = []                    # extra targets, e.g. ["numpy.linalg.*", "mymodule.solver"]
instrumentation = "hybrid"      # hybrid (patch+monitor) | patch | monitor | taint (hybrid+T3)
mode = "summary"                # summary | metadata
capture_backtrace = true
store_arrays = "auto"          # auto | always | never; enables element-wise sig
array_store_threshold = 100000 # max elements per stored array in auto mode
array_backend = "auto"         # auto | npy | zarr (compressed; pip install pytracer[arrays])

[storage]
output_dir = ".pytracer/runs"

[analysis]
alignment = "callsite"          # strict | callsite | fuzzy

# Per-run environment for an external perturbation backend; values may use
# {run_index} and {run_id}. Example:
# [perturb.env]
# VFC_BACKENDS = "libinterflop_mca.so --mode=mca --seed={run_index}"

[report]
formats = ["markdown", "html", "json"]
"""


def load_config(directory: str | Path | None = None) -> PytracerConfig:
    """Load configuration from pytracer.toml in *directory* (default: cwd).

    Returns built-in defaults when no config file exists.
    """
    base = Path(directory) if directory is not None else Path.cwd()
    path = base / CONFIG_FILENAME
    if not path.is_file():
        return PytracerConfig()
    try:
        with open(path, "rb") as fo:
            data = tomllib.load(fo)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    except OSError as e:
        raise ConfigError(f"{path}: cannot read: {e}") from e
    return config_from_dict(data, source=str(path))


def write_default_config(directory: str | Path | None = None, force: bool = False) -> Path:
    base = Path(directory) if directory is not None else Path.cwd()
    path = base / CONFIG_FILENAME
    if path.exists() and not force:
        raise ConfigError(f"{path} already exists (use --force to overwrite)")
    path.write_text(DEFAULT_TOML)
    return path
