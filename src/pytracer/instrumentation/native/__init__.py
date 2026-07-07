"""Tier T5 — native kernel census: build the LD_PRELOAD shim, parse its logs.

Linux-only, requires a C compiler, and only observes dynamically linked
BLAS/LAPACK symbols. Everything degrades to a reported note, never an error:
the census is a coverage instrument, not a required tier.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

NATIVE_LOG_FILENAME = "native_kernels.log"

_GEMM_SYMBOLS = ("cblas_dgemm", "cblas_sgemm", "dgemm_",
                 "scipy_cblas_dgemm64_", "scipy_cblas_sgemm64_", "scipy_dgemm_64_")


def shim_source() -> Path:
    return Path(__file__).parent / "blas_shim.c"


def ensure_shim(cache_dir: str | Path | None = None) -> tuple[Path | None, str]:
    """Compile (or reuse) the shim. Returns (path, reason-if-unavailable)."""
    if sys.platform != "linux":
        return None, "native census requires Linux (LD_PRELOAD)"
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        return None, "no C compiler (cc/gcc) found"
    source = shim_source()
    if not source.is_file():
        return None, f"shim source missing: {source}"

    cache = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "pytracer"
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.blake2b(source.read_bytes(), digest_size=8).hexdigest()
    out = cache / f"blas_shim-{digest}.so"
    if out.is_file():
        return out, ""
    proc = subprocess.run(
        [compiler, "-shared", "-fPIC", "-O2", "-o", str(out), str(source), "-ldl"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, f"shim compilation failed: {proc.stderr.strip()[:500]}"
    return out, ""


def find_real_blas_libs() -> list[str]:
    """Paths of BLAS libraries the shim may need to resolve against
    (numpy/scipy wheels load their bundled openblas RTLD_LOCAL)."""
    libs: list[str] = []
    for module_name in ("numpy", "scipy"):
        try:
            module = __import__(module_name)
        except ImportError:
            continue
        libs_dir = Path(module.__file__).parent.parent / f"{module_name}.libs"
        if libs_dir.is_dir():
            libs.extend(
                str(p) for p in sorted(libs_dir.glob("*openblas*"))
            )
    return libs


def parse_native_log(path: str | Path) -> dict[str, dict]:
    """Aggregate a shim log into {symbol: {calls, volume}}.

    volume is sum(m*n*k) for GEMM symbols (a flop-count proxy), sum(m*n)
    otherwise.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    kernels: dict[str, dict] = defaultdict(lambda: {"calls": 0, "volume": 0})
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        name = parts[0]
        try:
            m, n, k = (int(p) for p in parts[1:])
        except ValueError:
            continue
        entry = kernels[name]
        entry["calls"] += 1
        entry["volume"] += m * n * (k if name in _GEMM_SYMBOLS else 1)
    return dict(kernels)
