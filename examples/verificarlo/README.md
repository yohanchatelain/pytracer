# Tracing under Verificarlo (Monte Carlo Arithmetic)

Pytracer localizes variability; [Verificarlo](https://github.com/verificarlo/verificarlo)
creates it, by compiling numerical code with stochastic (MCA) arithmetic.
The `verificarlo/fuzzy` Docker images ship Python/NumPy/SciPy built with MCA
instrumentation, so every floating-point operation is randomly perturbed at
the given virtual precision.

## Workflow

Inside a fuzzy container (e.g. `verificarlo/fuzzy:latest-lab`):

```bash
pip install /path/to/pytracer[arrays]
cd /your/project
cp /path/to/pytracer/examples/verificarlo/pytracer.toml .
pytracer run your_script.py --repeat 20
pytracer report .pytracer/runs/latest
```

The `pytracer.toml` here rotates the MCA seed per run so the 20 repetitions
are independent samples of the stochastic arithmetic:

```toml
[perturb.env]
VFC_BACKENDS = "libinterflop_mca.so --mode=mca --precision-binary64=53 --seed={run_index}"
```

Element-wise significant digits computed by pytracer across those runs are
then a direct estimate of the MCA significant bits of every traced value —
the same quantity the `significantdigits` package estimates, localized per
function and argument.

## Sanity checks

- `pytracer doctor` reports whether a perturbation backend is detected
  (`VFC_*` environment variables).
- Run once with `[perturb.env]` removed and `--alignment strict`: an
  IEEE-deterministic build must show 53 bits everywhere and zero divergence.
  If it does not, the variability you saw was not MCA.

## Notes

- Pytracer never sets `VFC_BACKENDS` unless you configure it; it only
  templates `{run_index}`/`{run_id}` into values you provide.
- The native census (`--native`) composes with Verificarlo: `LD_PRELOAD`
  entries are prepended, not replaced.
