"""Exception hierarchy. Library code raises; only the CLI calls sys.exit."""


class PytracerError(Exception):
    """Base class for all pytracer errors."""


class ConfigError(PytracerError):
    """Invalid or unreadable configuration."""


class TargetResolutionError(PytracerError):
    """A trace target could not be resolved to a live object."""


class AlignmentError(PytracerError):
    """Runs could not be aligned under the requested mode."""


class ExperimentError(PytracerError):
    """Experiment orchestration failure (run directory, subprocess, ...)."""
