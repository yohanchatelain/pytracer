<p align="center">
  <img src="images/logo.png" alt="Pytracer Logo" width="240">
</p>

<h1 align="center">Pytracer</h1>

<p align="center">
  <strong>Numerical variability profiler for Python scientific programs</strong>
</p>

<p align="center">
  <a href="https://github.com/yohanchatelain/pytracer/releases"><img src="https://img.shields.io/badge/release-v2.0.1-blue.svg" alt="Release"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg" alt="Python Version"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/package%20manager-uv-purple.svg" alt="uv"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License"></a>
</p>

---

**Pytracer** profiles numerical stability across repeated executions of Python scientific workloads (under stochastic arithmetic such as [Verificarlo](https://github.com/verificarlo/verificarlo) / [Verrou](https://github.com/edf-hpc/verrou), seed rotation, or input perturbation). It captures function and array boundaries across 5 instrumentation tiers, aligns call sequences across runs, and ranks functions by **digit-loss amplification** ($\min \text{sig}_{\text{in}} - \min \text{sig}_{\text{out}}$) to pinpoint the exact callsites that destroy floating-point precision or trigger control-flow divergence.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Python API](#python-api)
- [CLI Cheat Sheet](#cli-cheat-sheet)
- [Documentation (`docs/`)](#documentation)
- [Development](#development)
- [Citation](#citation)
- [License](#license)

---

## Installation

Requires **Python $\ge$ 3.12** ([`uv`](https://github.com/astral-sh/uv) recommended):

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[all]"
```

Optional extras can be installed selectively: `pytracer[arrays]` (Zarr storage), `pytracer[plugins]` (scikit-learn), `pytracer[sig]` (`significantdigits`), `pytracer[gui]` (Dash/Plotly dashboard), or `pytracer[dev]`.

---

## Quick Start

```bash
# 1. Run 5 independent repetitions on a script (pass script arguments after --)
pytracer run examples/cancellation.py --repeat 5

# 2. Inspect reports (Markdown, HTML, and machine-readable JSON)
cat .pytracer/runs/latest/report/report.md
cat .pytracer/runs/latest/analysis/top_unstable.json

# 3. Gate CI on minimum significant bits (24 bits ≈ float32) and NaN/Inf absence
pytracer check .pytracer/runs/latest --min-sig-bits 24 --no-nan --no-inf

# 4. Launch the interactive Dash/Plotly web dashboard
pytracer dashboard .pytracer/runs/latest
```

---

## Python API

Importing `pytracer` has zero side effects and acts as a no-op outside `pytracer run`:

```python
import numpy as np
import pytracer

@pytracer.trace_function
def custom_step(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Explicitly traced (Tier T1) when executed under `pytracer run`."""
    return np.linalg.solve(a, b)

def operator_pipeline(x: np.ndarray) -> np.ndarray:
    """Wrap array in TracedArray (Tier T3) to trace +, -, @, and ufuncs."""
    tx = pytracer.taint(x)
    return (tx @ tx.T) + 1e-6
```

---

## CLI Cheat Sheet

All commands accept `-c / --config PATH` (defaults to `./pytracer.toml` if present). See **[`docs/cli-and-config.md`](docs/cli-and-config.md)** for all flags.

| Command | Purpose |
|---|---|
| `pytracer init [--force]` | Write a starter `pytracer.toml` in the current directory |
| `pytracer run SCRIPT [opts] [-- ARGS...]` | Run `N` isolated repetitions (`--repeat N`), align, analyze, and report |
| `pytracer analyze EXP_DIR` | (Re)compute sequence alignment (`strict`, `callsite`, `fuzzy`) and aggregations |
| `pytracer report EXP_DIR` | (Re)generate `markdown`, `html`, and `json` reports |
| `pytracer check EXP_DIR [opts]` | CI gate: exit `1` on precision loss, divergence, or NaN/Inf instability |
| `pytracer diff EXP_A EXP_B` | Compare baseline (`A`) vs. candidate (`B`) experiments (`--fail-on-regression`) |
| `pytracer dashboard EXP_DIR` | Launch interactive web UI (`--compare EXP_B` for A/B view) |
| `pytracer export EXP_DIR` | Export call spans to Chrome / [Perfetto](https://ui.perfetto.dev) trace JSON |
| `pytracer suggest-targets EXP_DIR` | Suggest `targets = [...]` from the Tier 4 `sys.monitoring` C-callable census |
| `pytracer plugins {list,targets} [NAME]` | List built-in plugins (`numpy`, `scipy`, `sklearn`) or their traced targets |
| `pytracer config {show,validate}` | Print resolved config as JSON or validate `pytracer.toml` |
| `pytracer doctor` | Check Python version, `sys.monitoring`, BLAS/compiler, and `VFC_*` environment |
| `pytracer clean` | Remove `.pytracer/runs/` experiment directories |

---

## Documentation

Detailed guides live in **[`docs/`](docs/README.md)** to keep this README concise:

| Document | Contents |
|---|---|
| **[CLI & Configuration Reference](docs/cli-and-config.md)** | Full CLI flag reference, `pytracer.toml` schema, `pytracer-thresholds.toml`, and Verificarlo/Verrou perturbation templates |
| **[Architecture & Metrics](docs/architecture-and-metrics.md)** | 5-tier instrumentation (`T1`–`T5`), call-sequence alignment (`strict`, `callsite`, `fuzzy` LCS), `element` vs. `summary` significant bits, amplification bits, and blind spots |
| **[Agent & Data Format Guide](docs/agent-and-data-guide.md)** | Non-interactive diagnostic workflows for AI agents & CI, exit codes, `.pytracer/runs/<id>/` directory layout, and JSON/Parquet schemas |
| **[Interactive Dashboard Guide](docs/dashboard.md)** | Overview, Explorer, Call Graph, Timeline, Coverage, and Runs tabs, plus `--compare` A/B mode |
| **[Examples Gallery](examples/README.md)** | Paired unstable vs. stable implementations of classical numerical pathologies (`examples/*.py` and `examples/verificarlo/`) |

---

## Development

```bash
uv run ruff check src tests examples   # Lint
uv run mypy src                        # Type-check
uv run pytest -q                       # Unit & integration test suite
uv run python benchmarks/bench.py      # Micro-benchmarks
```

---

## Citation

If you use Pytracer in your research, please cite the published paper:

> Yohan Chatelain, Nigel Yong, Gregory Kiar, and Tristan Glatard. “PyTracer: Automatically Profiling Numerical Instabilities in Python.” *IEEE Transactions on Computers*, 72(6):1792–1803, 2023. [https://doi.org/10.1109/TC.2022.3225929](https://doi.org/10.1109/TC.2022.3225929)

```bibtex
@article{chatelain2023pytracer,
  author  = {Chatelain, Yohan and Yong, Nigel and Kiar, Gregory and Glatard, Tristan},
  title   = {{PyTracer}: Automatically Profiling Numerical Instabilities in {Python}},
  journal = {IEEE Transactions on Computers},
  volume  = {72},
  number  = {6},
  pages   = {1792--1803},
  year    = {2023},
  doi     = {10.1109/TC.2022.3225929}
}
```

---

## License

Pytracer is released under the [MIT License](LICENSE).
