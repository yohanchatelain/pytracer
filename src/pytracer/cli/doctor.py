"""pytracer doctor — make setup issues obvious.

Exit code is nonzero only for critical failures; missing optional
dependencies are warnings.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _version_of(dist: str) -> str | None:
    try:
        return importlib_metadata.version(dist)
    except importlib_metadata.PackageNotFoundError:
        return None


def run_checks(directory: str | Path | None = None) -> list[dict]:
    checks: list[dict] = []
    base = Path(directory) if directory else Path.cwd()

    py = sys.version_info
    if py >= (3, 12):
        checks.append(_check("python", OK, f"Python {sys.version.split()[0]}"))
    else:
        checks.append(
            _check(
                "python",
                WARN,
                f"Python {sys.version.split()[0]}: sys.monitoring (T4) needs 3.12+; "
                "the monitor tier will be disabled",
            )
        )

    for dist in ("numpy", "wrapt", "msgspec"):
        v = _version_of(dist)
        checks.append(
            _check(dist, OK if v else FAIL, f"{dist} {v}" if v else f"{dist} not installed")
        )
    for dist in ("pyarrow", "scipy", "scikit-learn", "zarr", "significantdigits", "dash"):
        v = _version_of(dist)
        checks.append(
            _check(dist, OK if v else WARN, f"{dist} {v}" if v else f"{dist} not installed")
        )

    if importlib.util.find_spec("numpy") is not None:
        try:
            import numpy as np

            blas = "unknown"
            try:
                info = np.show_config(mode="dicts")  # numpy >= 1.26
                blas = info.get("Build Dependencies", {}).get("blas", {}).get("name", "unknown")
            except TypeError:
                pass
            checks.append(_check("blas", OK, f"numpy {np.__version__}, BLAS: {blas}"))
        except Exception as e:
            checks.append(_check("blas", WARN, f"could not inspect numpy BLAS: {e}"))

    if os.access(base, os.W_OK):
        checks.append(_check("writable", OK, f"{base} is writable"))
    else:
        checks.append(_check("writable", FAIL, f"{base} is not writable"))

    config_path = base / "pytracer.toml"
    if config_path.is_file():
        try:
            from pytracer.config.loader import load_config

            config = load_config(base)
            checks.append(
                _check(
                    "config",
                    OK,
                    f"pytracer.toml valid (plugins: {config.trace.plugins})",
                )
            )
        except Exception as e:
            checks.append(_check("config", FAIL, f"pytracer.toml invalid: {e}"))
    else:
        checks.append(_check("config", OK, "no pytracer.toml (defaults apply)"))

    perturb = [k for k in os.environ if k.startswith(("VFC_", "VERROU_"))]
    if perturb or os.environ.get("LD_PRELOAD"):
        checks.append(_check("perturbation", OK, f"backend detected: {perturb or 'LD_PRELOAD'}"))
    else:
        checks.append(
            _check(
                "perturbation",
                WARN,
                "no perturbation backend detected (VFC_*/VERROU_*/LD_PRELOAD); "
                "identical runs will show no variability",
            )
        )
    return checks


def format_checks(checks: list[dict]) -> str:
    symbols = {OK: "+", WARN: "!", FAIL: "x"}
    return "\n".join(f"{symbols[c['status']]} {c['detail']}" for c in checks)


def exit_code(checks: list[dict]) -> int:
    return 1 if any(c["status"] == FAIL for c in checks) else 0
