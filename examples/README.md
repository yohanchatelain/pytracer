# Examples: classical numerical-accuracy pathologies

Each script pairs an **unstable** formulation with its **stable**
counterpart, both traced with `@pytracer.trace_function`. A tiny unseeded
input perturbation per run stands in for stochastic arithmetic, so the
examples show real variability without a perturbation backend — under
Verificarlo/fuzzy (see `verificarlo/`) the same scripts localize true
floating-point instability.

Run any of them with:

```bash
pytracer run examples/<name>.py --repeat 5
```

and the unstable variant ranks at the top of the report with low
significant bits and high amplification, while its stable twin tracks only
the injected perturbation.

| Script | Phenomenon | Unstable | Stable |
|---|---|---|---|
| `cancellation.py` | catastrophic cancellation in E[x²]−E[x]² variance | `naive_variance` | `stable_variance` (`np.var`) |
| `quadratic_roots.py` | cancellation in the quadratic formula's small root | `naive_small_root` | `stable_small_root` (conjugate form) |
| `summation_order.py` | non-associativity of FP summation under reordering | `naive_running_sum` | `exact_fsum` (Shewchuk) |
| `ill_conditioned_solve.py` | conditioning: Hilbert matrix, cond ≈ 1e13 | `solve_hilbert` | `solve_well_conditioned` |
| `finite_differences.py` | step-size dilemma: roundoff vs truncation | `forward_diff_tiny_h` | `central_diff_optimal_h` |
| `expm1_log1p.py` | cancellation in exp(x)−1 and log(1+x) for tiny x | `naive_expm1`, `naive_log1p` | `library_expm1`, `library_log1p` |
| `polynomial_eval.py` | cancellation near a multiple root, expanded vs factored | `expanded_poly` | `factored_poly` |
| `simple_numpy.py` | determinism baseline: must show 53 bits, zero divergence | — | — |

These pairs are also pytracer's own regression suite: an integration test
runs each example and asserts the unstable variant loses significantly
more bits than the stable one (`tests/integration/test_examples.py`) — if
pytracer stops detecting a classic pathology, CI fails.
