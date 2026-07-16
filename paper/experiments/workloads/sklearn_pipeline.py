"""Scikit-learn case-study workload: StandardScaler + PCA +
LogisticRegression on near-collinear synthetic data.

Run-to-run variability is induced by unseeded RNG jitter on the inputs
(the same perturbation model as the examples gallery); under a
stochastic-arithmetic backend the jitter can be removed and the identical
pipeline measures true floating-point instability.

The feature matrix is deliberately ill-conditioned: duplicated columns
separated by a tiny jitter make the covariance matrix nearly singular,
stressing PCA's eigendecomposition and the logistic-regression solver.
"""

import sys

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

dtype = np.float32 if "--float32" in sys.argv else np.float64

# The dataset is fixed across runs; only a tiny unseeded jitter differs
# per run, playing the role of the input perturbation.
rng_data = np.random.default_rng(42)
rng_perturb = np.random.default_rng()  # unseeded: the perturbation source

n, p = 400, 11
base = rng_data.normal(size=(n, p))
# one near-collinear pair: the last column duplicates the first up to
# ~1e-4 noise, so exactly one pair of covariance eigenvalues is nearly
# degenerate while the rest of the spectrum stays well separated
X = np.hstack([base, base[:, :1] + rng_data.normal(scale=1e-4, size=(n, 1))])
w = rng_data.normal(size=X.shape[1])
y = (X @ w + 0.1 * rng_data.normal(size=n) > 0).astype(int)

# Per-run input perturbation. The jitter must be representable in both
# dtypes under study (float32 ulp ~ 1.2e-7), and stay well below the
# collinear-block separation so it perturbs rather than redefines the data.
X = X * (1.0 + rng_perturb.normal(scale=3e-7, size=X.shape))
X = X.astype(dtype)

scaler = StandardScaler()
Xs = scaler.fit_transform(X)

pca = PCA(n_components=8)
Z = pca.fit(Xs).transform(Xs)

clf = LogisticRegression(max_iter=500)
clf.fit(Z, y)
proba = clf.predict_proba(Z)

print("explained variance ratio:", pca.explained_variance_ratio_[:4])
print("mean p(y=1):", float(proba[:, 1].mean()))
