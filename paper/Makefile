PY := ../.venv-paper/bin/python

RESULTS := results/e1_gallery.csv results/e2_overhead.csv results/e3_coverage.csv \
           results/e4_alignment.csv results/e5_basis.csv results/e6_case.csv \
           results/e0_v1_matrix.csv results/e7_storage.csv

.PHONY: all experiments tables figures pdf clean

all: pdf

experiments:
	$(PY) experiments/e1_gallery.py
	$(PY) experiments/e2_overhead.py
	$(PY) experiments/e3_coverage.py
	$(PY) experiments/e4_alignment.py
	$(PY) experiments/e5_basis.py
	$(PY) experiments/e6_sklearn_case.py
	$(PY) experiments/e0_v1_matrix.py
	$(PY) experiments/e7_storage.py

tables:
	$(PY) experiments/make_tables.py

figures:
	$(PY) experiments/make_figures.py

pdf:
	@command -v latexmk >/dev/null 2>&1 \
	  && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex \
	  || echo "latexmk not installed; main.tex + tables/ + figures/ are complete (see README.md)"

clean:
	latexmk -C main.tex 2>/dev/null || true
	rm -f main.bbl
