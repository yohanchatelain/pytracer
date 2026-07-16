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

rng = np.random.default_rng()  # unseeded: the perturbation source

n, p = 400, 12
base = rng.normal(size=(n, p // 2))
# near-collinear block: each column duplicated with ~1e-7 relative jitter
X = np.hstack([base, base + rng.normal(scale=1e-7, size=base.shape)])
X = X.astype(dtype)
w = rng.normal(size=X.shape[1])
y = (X @ w + 0.1 * rng.normal(size=n) > 0).astype(int)

scaler = StandardScaler()
Xs = scaler.fit_transform(X)

pca = PCA(n_components=8)
Z = pca.fit(Xs).transform(Xs)

clf = LogisticRegression(max_iter=500)
clf.fit(Z, y)
proba = clf.predict_proba(Z)

print("explained variance ratio:", pca.explained_variance_ratio_[:4])
print("mean p(y=1):", float(proba[:, 1].mean()))
