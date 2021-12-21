import os
from enum import IntEnum, auto

from pytracer.core.config import config as cfg
from pytracer.core.config import constant
from pytracer.utils.singleton import Singleton


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

    parameters = {}
    type_default = IOType.PICKLE
    cache_default = {"root": constant.cache.root,
                     "traces": constant.cache.traces,
                     "stats": constant.cache.stats,
                     "sources": constant.cache.sources,
                     "info": constant.cache.info,
                     "report": constant.cache.report,
                     "trace": constant.trace.filename,
                     "callgraph": constant.callgraph.filename,
                     "export": constant.export.filename
                     }

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

        self.cache_info = self._get_parameters(
            cfg.io.cache.info, self.cache_default["info"])

        self.cache_report = self._get_parameters(
            cfg.io.cache.report, self.cache_default["report"])

        self.trace = self._get_parameters(
            cfg.io.trace, self.cache_default['trace'])

        self.export = self._get_parameters(
            cfg.io.export.filename, self.cache_default["export"])

        self.callgraph = self._get_parameters(
            cfg.io.stats.callgraph, self.cache_default["callgraph"])

    def mkdir_cache(self):
        self.cache_path = os.path.abspath(self.cache_root)
        if not os.path.isdir(self.cache_path):
            os.makedirs(self.cache_path, exist_ok=True)

        self.cache_traces_path = os.path.join(
            self.cache_path, self.cache_traces)
        if not os.path.isdir(self.cache_traces_path):
            os.makedirs(self.cache_traces_path, exist_ok=True)

        self.cache_stats_path = os.path.join(self.cache_path, self.cache_stats)
        if not os.path.isdir(self.cache_stats_path):
            os.makedirs(self.cache_stats_path, exist_ok=True)

        self.cache_sources_path = os.path.join(
            self.cache_path, self.cache_sources)
        if not os.path.isdir(self.cache_sources_path):
            os.makedirs(self.cache_sources_path, exist_ok=True)

        self.cache_info_path = os.path.join(self.cache_path, self.cache_info)
        if not os.path.isdir(self.cache_info_path):
            os.makedirs(self.cache_info_path, exist_ok=True)

        self.cache_report_path = os.path.join(
            self.cache_path, self.cache_report)
        if not os.path.isdir(self.cache_report_path):
            os.makedirs(self.cache_report_path, exist_ok=True)

    def get_type(self):
        return self.type
