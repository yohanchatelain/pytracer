"""Example with a genuinely unstable computation.

`naive_variance` uses the textbook E[x^2] - E[x]^2 formula, which suffers
catastrophic cancellation when the mean is large relative to the variance.
Run-to-run variability is induced here with an unseeded RNG so the example
shows real variability even without a perturbation backend:

    pytracer run examples/cancellation.py --repeat 5 --target __main__.naive_variance

Under a stochastic-arithmetic environment (Verificarlo, fuzzy), drop the RNG
and the same structure localizes true floating-point instability.
"""

import os

import numpy as np

import pytracer


@pytracer.trace_function
def naive_variance(x):
    return float(np.mean(x * x) - np.mean(x) ** 2)


@pytracer.trace_function
def stable_variance(x):
    return float(np.var(x))


def main():
    run_id = os.environ.get("PYTRACER_RUN_ID", "")
    seed = int(run_id.split("-")[-1]) if run_id.startswith("run-") else None
    rng = np.random.default_rng(seed)  # per-run variability (deterministic per run_id)
    x = 1e8 + rng.standard_normal(10_000)

    naive = naive_variance(x)
    stable = stable_variance(x)
    print(f"naive variance:  {naive}")
    print(f"stable variance: {stable}")


if __name__ == "__main__":
    main()
