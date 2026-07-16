# Pytracer 2 paper draft

Technical paper draft for Pytracer 2 with a fully reproducible experiment
campaign. Every number in the paper flows from a CSV in `results/` produced
by a script in `experiments/`; tables (`tables/*.tex`) and figures
(`figures/*.pdf`) are generated, never hand-typed.

## Reproducing

```bash
# from the repository root
python3.13 -m venv .venv-paper
.venv-paper/bin/pip install -e ".[dev,arrays,sig]" matplotlib pandas scikit-learn scipy

cd paper
make experiments   # runs E0–E7, writes results/*.csv (~15–30 min)
make tables        # results/*.csv -> tables/*.tex
make figures       # results/*.csv -> figures/*.pdf
make pdf           # latexmk (texlive); skipped gracefully if not installed
```

## Experiments

| ID | Question | Script |
|----|----------|--------|
| E0 | Does Pytracer 1 still install/run on modern Python? | `e0_v1_matrix.py` |
| E1 | Does Pytracer 2 detect and rank all 8 classical pathologies? | `e1_gallery.py` |
| E2 | What is the per-tier tracing overhead? | `e2_overhead.py` |
| E3 | What does the coverage report show across tier combinations? | `e3_coverage.py` |
| E4 | How do alignment strategies behave under control-flow divergence? | `e4_alignment.py` |
| E5 | How optimistic is the sig(mean) proxy vs element-wise digits? | `e5_basis.py` |
| E6 | End-to-end sklearn case study + numerical CI (`check`/`diff`) | `e6_sklearn_case.py` |
| E7 | Storage footprint and crash-safety | `e7_storage.py` |

## Perturbation source

In this environment no stochastic-arithmetic backend (Verificarlo/Verrou)
is installed; run-to-run variability is induced by unseeded RNG input
perturbation, exactly as in the repository's example gallery and CI. The
identical workflow, run inside a `verificarlo/fuzzy` container with
`[perturb.env]` seed rotation (see `examples/verificarlo/`), measures true
floating-point instability under MCA. The paper states this explicitly.
