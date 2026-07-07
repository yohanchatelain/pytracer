"""Pytracer 2 — numerical variability profiler for Python scientific programs.

Importing this package has no side effects: no configuration is read, no
files are created, no logging is configured.
"""

__version__ = "2.0.0a0"

__all__ = ["__version__", "trace_function", "taint", "PytracerError"]


def __getattr__(name):
    # Lazy exports keep `import pytracer` free of numpy/wrapt imports.
    if name == "trace_function":
        from pytracer.instrumentation.decorator import trace_function

        return trace_function
    if name == "taint":
        from pytracer.instrumentation.tracer_array import taint

        return taint
    if name == "PytracerError":
        from pytracer._errors import PytracerError

        return PytracerError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
