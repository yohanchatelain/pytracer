"""T5 native BLAS census: LD_PRELOAD shim end-to-end.

Skipped when the platform can't build/use the shim (non-Linux, no cc).
"""

import json
import shutil
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "linux", reason="LD_PRELOAD census is Linux-only"),
    pytest.mark.skipif(
        shutil.which("cc") is None and shutil.which("gcc") is None,
        reason="no C compiler",
    ),
]


def test_shim_builds_and_parses(tmp_path):
    from pytracer.instrumentation.native import ensure_shim, parse_native_log

    shim, reason = ensure_shim(cache_dir=tmp_path)
    assert shim is not None, reason
    assert shim.is_file()

    log = tmp_path / "kernels.log"
    log.write_text("scipy_cblas_dgemm64_ 10 20 30\nscipy_cblas_dgemm64_ 10 20 30\n"
                   "scipy_dgesv_64_ 5 1 0\ngarbage line\n")
    parsed = parse_native_log(log)
    assert parsed["scipy_cblas_dgemm64_"] == {"calls": 2, "volume": 12000}
    assert parsed["scipy_dgesv_64_"]["calls"] == 1


def test_native_census_end_to_end(tmp_path):
    script = tmp_path / "gemm_heavy.py"
    script.write_text(
        "import numpy as np\n"
        "a = np.ones((40, 50)); b = np.ones((50, 60))\n"
        "c = a @ b\n"
        "x = np.linalg.solve(np.eye(8) * 2.0, np.ones(8))\n"
        "print(float(c.sum()), float(x.sum()))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytracer.cli.main", "run", "gemm_heavy.py",
         "--repeat", "2", "--plugins", "--target", "numpy.linalg.solve", "--native"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr

    root = tmp_path / ".pytracer" / "runs"
    (exp,) = [
        p for p in root.iterdir()
        if p.is_dir() and not p.is_symlink() and (p / ".pytracer-experiment").exists()
    ]
    # per-run kernel logs exist and contain a gemm
    for run_dir in sorted((exp / "runs").iterdir()):
        log = run_dir / "native_kernels.log"
        assert log.is_file(), f"no native log in {run_dir}"
        assert "gemm" in log.read_text()

    coverage = json.loads((exp / "analysis" / "coverage.json").read_text())
    kernels = coverage["native_kernels"]
    assert any("gemm" in name for name in kernels)
    assert any("gesv" in name for name in kernels)
    gemm = next(v for k, v in kernels.items() if "gemm" in k)
    assert gemm["calls"] == 2  # one matmul per run
    assert gemm["volume"] == 2 * 40 * 60 * 50

    report = (exp / "report" / "report.md").read_text()
    assert "Native BLAS/LAPACK kernels" in report
