"""Built-in plugin registry."""

from __future__ import annotations

from pytracer._errors import ConfigError
from pytracer.plugins.base import PytracerPlugin, TraceTarget


def _numpy_plugin() -> PytracerPlugin:
    functions = [
        "numpy.sum",
        "numpy.mean",
        "numpy.std",
        "numpy.var",
        "numpy.dot",
        "numpy.linalg.norm",
        "numpy.linalg.solve",
        "numpy.linalg.det",
        "numpy.linalg.eig",
        "numpy.linalg.eigh",
        "numpy.linalg.svd",
        "numpy.linalg.inv",
        "numpy.linalg.lstsq",
        "numpy.linalg.cholesky",
        "numpy.linalg.qr",
    ]
    # numpy.matmul is a ufunc; keep it in the ufunc list, not here.
    ufuncs = [
        "numpy.add",
        "numpy.subtract",
        "numpy.multiply",
        "numpy.true_divide",
        "numpy.matmul",
        "numpy.exp",
        "numpy.log",
        "numpy.sqrt",
        "numpy.power",
    ]
    targets = [TraceTarget(p, kind="function") for p in functions]
    targets += [TraceTarget(p, kind="ufunc") for p in ufuncs]
    return PytracerPlugin(name="numpy", requires="numpy", targets=targets)


def _scipy_plugin() -> PytracerPlugin:
    paths = [
        "scipy.linalg.solve",
        "scipy.linalg.lu",
        "scipy.linalg.qr",
        "scipy.linalg.svd",
        "scipy.linalg.eigh",
        "scipy.optimize.minimize",
        "scipy.optimize.root",
        "scipy.optimize.least_squares",
        "scipy.integrate.quad",
        "scipy.integrate.solve_ivp",
        "scipy.interpolate.interp1d",
    ]
    return PytracerPlugin(
        name="scipy", requires="scipy", targets=[TraceTarget(p) for p in paths]
    )


def _sklearn_plugin() -> PytracerPlugin:
    paths = [
        "sklearn.linear_model.LinearRegression.fit",
        "sklearn.linear_model.LinearRegression.predict",
        "sklearn.linear_model.LogisticRegression.fit",
        "sklearn.linear_model.LogisticRegression.predict",
        "sklearn.svm.SVC.fit",
        "sklearn.decomposition.PCA.fit",
        "sklearn.decomposition.PCA.transform",
        "sklearn.cluster.KMeans.fit",
    ]
    return PytracerPlugin(
        name="sklearn",
        requires="sklearn",
        targets=[TraceTarget(p, kind="method") for p in paths],
    )


_BUILTIN = {
    "numpy": _numpy_plugin,
    "scipy": _scipy_plugin,
    "sklearn": _sklearn_plugin,
}


def available_plugins() -> list[str]:
    return sorted(_BUILTIN)


def get_plugin(name: str) -> PytracerPlugin:
    try:
        return _BUILTIN[name]()
    except KeyError:
        raise ConfigError(
            f"unknown plugin {name!r}; available plugins: {available_plugins()}"
        ) from None


def targets_for(plugin_names: list[str], extra_targets: list[str]) -> tuple[list[str], list[str]]:
    """Expand plugin names + explicit targets into a spec list.

    Returns (specs, warnings). Plugins whose library is not installed are
    skipped with a warning rather than an error.
    """
    specs: list[str] = []
    warnings: list[str] = []
    for name in plugin_names:
        plugin = get_plugin(name)
        if not plugin.available():
            warnings.append(f"plugin {name!r} skipped: {plugin.requires} is not installed")
            continue
        specs.extend(plugin.target_specs())
    for target in extra_targets:
        if target not in specs:
            specs.append(target)
    return specs, warnings
