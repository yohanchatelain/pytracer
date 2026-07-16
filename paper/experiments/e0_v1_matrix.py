"""E0 — Can Pytracer 1 still be installed and run on modern Python?

Pytracer 1 was never published to PyPI (the `pytracer` name there belongs
to an unrelated project), so it is installed from the archived source at
git commit ed755c7 — the final v1 revision. For each available CPython
(3.10–3.13): install v1 into a fresh venv together with best-effort
*modern* versions of its undeclared dependencies, then try (a) importing
the package and (b) starting the CLI (`python -m pytracer`). The recorded
failure mode per interpreter is the motivation table for the rewrite (v1
declares no install_requires and pins a ~2021 stack in requirements.txt).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from common import REPO, main_guard, write_csv

PYTHONS = ["3.10", "3.11", "3.12", "3.13"]
UV = Path.home() / ".local" / "bin" / "uv"
V1_COMMIT = "ed755c7"

# Modern stand-ins for the imports v1 makes but never declares.
MODERN_DEPS = ["numpy", "dash", "click", "click-log", "psutil", "networkx",
               "astunparse", "pandas", "plotly", "tables", "dill", "scipy",
               "scikit-learn"]


def probe(cmd: list[str], cwd: Path, timeout: int = 180,
          env: dict | None = None) -> tuple[int, str]:
    import os
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout,
                              env={**os.environ, **(env or {})})
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except FileNotFoundError as exc:
        return -2, str(exc)


def first_error_line(output: str) -> str:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith(("ModuleNotFoundError", "ImportError", "AttributeError",
                            "SyntaxError", "TypeError", "ValueError", "error:")):
            return line
    return output.splitlines()[-1][:120] if output else ""


def export_v1_source() -> Path:
    src = Path(tempfile.mkdtemp(prefix="pytracer1-src-"))
    tar = subprocess.run(["git", "archive", V1_COMMIT], cwd=REPO,
                         capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(src)], input=tar.stdout, check=True)
    return src


def run() -> int:
    v1_src = export_v1_source()
    rows = []
    for version in PYTHONS:
        python = f"/usr/bin/python{version}"
        if not Path(python).exists():
            continue
        workdir = Path(tempfile.mkdtemp(prefix=f"pytracer1-{version}-"))
        venv = workdir / "venv"
        subprocess.run([str(UV), "venv", "--python", python, str(venv)],
                       capture_output=True, check=True)
        vpy = venv / "bin" / "python"

        rc_install, out_install = probe(
            [str(UV), "pip", "install", "--python", str(vpy),
             str(v1_src), *MODERN_DEPS], workdir, timeout=600)

        # Stage 1: bare import — v1 refuses without a PYTRACER_CONFIG env var
        # (an import-time side effect in itself).
        rc_bare, out_bare = probe(
            [str(vpy), "-c", "import pytracer.core.config"], workdir)
        # Stage 2: with the shipped default config supplied.
        cfg = {"PYTRACER_CONFIG": str(v1_src / "pytracer" / "data" / "config"
                                      / "config.json")}
        rc_import, out_import = probe(
            [str(vpy), "-c", "import pytracer.core.config"], workdir, env=cfg)
        rc_cli, out_cli = probe(
            [str(vpy), "-m", "pytracer", "--help"], workdir, env=cfg)

        # Stage 3: the actual product — trace and parse a 3-line numpy
        # program on the modern stack.
        script = workdir / "tiny.py"
        script.write_text(
            "import numpy as np\nprint(np.sum(np.arange(10.0)))\n")
        rc_trace, out_trace = probe(
            [str(vpy), "-m", "pytracer", "trace", "--command", str(script)],
            workdir, env=cfg, timeout=300)
        rc_parse, out_parse = (-3, "skipped: trace failed")
        if rc_trace == 0:
            rc_parse, out_parse = probe(
                [str(vpy), "-m", "pytracer", "parse"], workdir, env=cfg,
                timeout=300)

        rows.append({
            "python": version,
            "install_ok": rc_install == 0,
            "install_error": "" if rc_install == 0 else first_error_line(out_install),
            "bare_import_ok": rc_bare == 0,
            "bare_import_error": "" if rc_bare == 0 else first_error_line(out_bare),
            "import_ok": rc_import == 0,
            "import_error": "" if rc_import == 0 else first_error_line(out_import),
            "cli_ok": rc_cli == 0,
            "cli_error": "" if rc_cli == 0 else first_error_line(out_cli),
            "trace_ok": rc_trace == 0,
            "trace_error": "" if rc_trace == 0 else first_error_line(out_trace),
            "parse_ok": rc_parse == 0,
            "parse_error": "" if rc_parse == 0 else first_error_line(out_parse),
        })
        print(f"py{version}: install={rc_install == 0} import={rc_import == 0} "
              f"cli={rc_cli == 0} trace={rc_trace == 0} parse={rc_parse == 0}")
        if rc_import != 0:
            print(f"  import: {first_error_line(out_import)}")
        if rc_trace != 0:
            print(f"  trace:  {first_error_line(out_trace)}")
        if rc_parse != 0:
            print(f"  parse:  {first_error_line(out_parse)}")

    write_csv("e0_v1_matrix.csv", rows)
    return 0


if __name__ == "__main__":
    main_guard(run)
