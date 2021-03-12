import os
from enum import IntEnum, auto

from pytracer.core.config import config as cfg
from pytracer.core.config import constant
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton

logger = get_logger()


class IOType(IntEnum):
    TEXT = auto()
    JSON = auto()
    PICKLE = auto()

    def from_string(string):
        if string == "text":
            return IOType.TEXT
        if string == "json":
            return IOType.JSON
        if string == "pickle":
            return IOType.PICKLE
        return None


class IOInitializer(metaclass=Singleton):

    parameters = dict()
    type_default = IOType.PICKLE
    filename_default = None
    cache_default = {"root": constant.cache.root,
                     "traces": constant.cache.traces,
                     "stats": constant.cache.stats,
                     "sources": constant.cache.sources
                     }
    export_default = constant.export

    def __init__(self):
        self.read_parameters()
        self.mkdir_cache()

    def _get_parameters(self, param, default):
        if param:
            return param
        return default

    def read_parameters(self):

        self.type = self._get_parameters(
            IOType.from_string(cfg.io.type), self.type_default)

        self.cache_root = self._get_parameters(
            cfg.io.cache.root, self.cache_default["root"])

        self.cache_traces = self._get_parameters(
            cfg.io.cache.traces, self.cache_default["traces"])

        self.cache_stats = self._get_parameters(
            cfg.io.cache.stats, self.cache_default["stats"])

        self.cache_sources = self._get_parameters(
            cfg.io.cache.sources, self.cache_default["sources"])

        self.filename = self._get_parameters(
            cfg.io.filename, self.filename_default)

        self.export = self._get_parameters(
            cfg.io.export, self.export_default)

    def mkdir_cache(self):
        self.cache_path = f"{os.getcwd()}{os.sep}{self.cache_root}"
        if not os.path.isdir(self.cache_path):
            os.makedirs(self.cache_path)
            logger.debug(f"cache directory created {self.cache_path}")

        self.cache_traces_path = f"{self.cache_path}{os.sep}{self.cache_traces}"
        if not os.path.isdir(self.cache_traces_path):
            os.makedirs(self.cache_traces_path)
            logger.debug(
                f"cache traces directory created {self.cache_traces_path}")

        self.cache_stats_path = f"{self.cache_path}{os.sep}{self.cache_stats}"
        if not os.path.isdir(self.cache_stats_path):
            os.makedirs(self.cache_stats_path)
            logger.debug(
                f"cache stats directory created {self.cache_stats_path}")

        self.cache_sources_path = f"{self.cache_path}{os.sep}{self.cache_sources}"
        if not os.path.isdir(self.cache_sources_path):
            os.makedirs(self.cache_sources_path)
            logger.debug(
                f"cache sources directory created {self.cache_sources_path}")

    def get_type(self):
        return self.type
