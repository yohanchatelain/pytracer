"""Hard rule (plan §10): importing pytracer must have zero side effects."""

import subprocess
import sys


def test_import_creates_nothing_and_needs_nothing(tmp_path):
    code = (
        "import os, pytracer; "
        "print(pytracer.__version__); "
        "print(sorted(os.listdir()))"
    )
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    version, listing = proc.stdout.strip().splitlines()
    assert version == "2.0.0a0"
    assert listing == "[]"  # nothing created in cwd


def test_import_is_lazy_about_numpy(tmp_path):
    code = "import sys, pytracer; print('numpy' in sys.modules)"
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"
