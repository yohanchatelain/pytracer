import datetime
import os
import pickle
from abc import abstractmethod
from collections import OrderedDict

import pytracer.core.inout._init as _init
import pytracer.utils as ptutils
from pytracer.core.config import constant
from pytracer.utils.singleton import Singleton


class PytracerInfoRegisterAbstract:

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def __str__(self):
        pass

    def set_pytracer_log(self, name, path):
        self._pytracer_log_name = name
        self._pytracer_log_path = path

    def set_args(self, args):
        self._pytracer_args = args


class PytracerInfoTraceRegister(PytracerInfoRegisterAbstract):

    def __init__(self):
        self._registration_date = datetime.datetime.now()
        self._init_default()

    def _init_default(self):
        self._trace_name = None
        self._trace_path = None
        self._pytracer_args = None
        self._report_name = None
        self._report_path = None
        self._pytracer_log_name = None
        self._pytracer_log_path = None

    def set_trace(self, name, path):
        self._trace_name = name
        self._trace_path = path

    def set_size(self):
        self._trace_size = os.stat(self._trace_path).st_size

    def get_trace_name(self):
        return self._trace_name

    def get_path_name(self):
        return self._path_name

    def set_report(self, name, path):
        self._report_name = name
        self._report_path = path

    def __str__(self):

        _str_fields = OrderedDict(
            Date=self._registration_date.ctime(),
            Name=self._trace_name,
            Path=self._trace_path,
            Size=ptutils.get_human_size(self._trace_size),
            ReportName=self._report_name,
            ReportPath=self._report_path,
            Args=self._pytracer_args,
            PytracerLogName=self._pytracer_log_name,
            PytracerLogPath=self._pytracer_log_path
        )

        _str_map = [f"{key:>15}:\t{value}\n" for key,
                    value in _str_fields.items()]
        _str = "".join(_str_map)

        return _str


class PytracerInfoAggregationRegister(PytracerInfoRegisterAbstract):

    def __init__(self):
        self._registration_date = datetime.datetime.now()
        self._init_default()

    def _init_default(self):
        self._aggregation_name = None
        self._aggregation_path = None
        self._pytracer_args = None
        self._traces = []

    def set_aggregation(self, name, path):
        self._aggregation_name = name
        self._aggregation_path = path

    def add_trace(self, trace):
        self._traces.append(trace)

    def add_traces(self, traces):
        for trace in traces:
            self.add_trace(trace)

    def set_size(self):
        self._aggregation_size = os.stat(self._aggregation_path).st_size

    def __str__(self):

        _str_fields = OrderedDict(
            Date=self._registration_date.ctime(),
            Name=self._aggregation_name,
            Path=self._aggregation_path,
            Size=ptutils.get_human_size(self._aggregation_size),
            Args=self._pytracer_args,
            Traces=self._traces,
            PytracerLogName=self._pytracer_log_name,
            PytracerLogPath=self._pytracer_log_path
        )

        _str_map = [f"{key:>15}:\t{value}\n" for key,
                    value in _str_fields.items()]
        _str = "".join(_str_map)

        return _str


class PytracerInfoRegister(metaclass=Singleton):

    def __init__(self):
        self.parameters = _init.IOInitializer()
        self._trace = PytracerInfoTraceRegister()
        self._aggregation = PytracerInfoAggregationRegister()

    def set_args(self, args):
        self._trace.set_args(args)
        self._aggregation.set_args(args)

    def set_trace(self, name, path):
        self._trace.set_trace(name, path)

    def set_report(self, name, path):
        self._trace.set_report(name, path)

    def add_trace(self, trace):
        self._aggregation.add_trace(trace)

    def add_traces(self, traces):
        self._aggregation.add_traces(traces)

    def set_pytracer_log(self, name, path):
        self._trace.set_pytracer_log(name, path)
        self._aggregation.set_pytracer_log(name, path)

    def set_aggregation(self, name, path):
        self._aggregation.set_aggregation(name, path)

    def set_trace_size(self):
        self._trace.set_size()

    def set_aggregation_size(self):
        self._aggregation.set_size()

    def _get_trace_registration_filename(self):
        path = self.parameters.cache_info_path
        filename = ptutils.get_filename(
            constant.register.trace, ext=constant.extension.pickle)
        return os.path.join(path, filename)

    def _get_aggregation_registration_filename(self):
        path = self.parameters.cache_info_path
        filename = ptutils.get_filename(
            constant.register.aggregation, ext=constant.extension.pickle)
        return os.path.join(path, filename)

    def register_trace(self):
        filename = self._get_trace_registration_filename()
        with open(filename, 'wb') as ostream:
            pickler = pickle.Pickler(ostream)
            pickler.dump(self._trace)

    def register_aggregation(self):
        filename = self._get_aggregation_registration_filename()
        with open(filename, 'wb') as ostream:
            pickler = pickle.Pickler(ostream)
            pickler.dump(self._aggregation)


class PytracerInfoPrinter(metaclass=Singleton):

    def __init__(self, args):
        self.parameters = _init.IOInitializer()
        self.args = args
        self._trace_info = self._get_trace_info()
        self._aggregation_info = self._get_aggregation_info()

    def _load_trace_info(self, trace_path):
        with open(trace_path, 'rb') as istream:
            unpickler = pickle.Unpickler(istream)
            return unpickler.load()

    def _load_aggregation_info(self, aggregation_path):
        with open(aggregation_path, 'rb') as istream:
            unpickler = pickle.Unpickler(istream)
            return unpickler.load()

    def _get_trace_info(self):
        path = self.parameters.cache_info_path
        _traces = os.listdir(path)
        if _traces == []:
            return []
        traces_path = [os.path.join(
            path, trace) for trace in _traces if trace.startswith(constant.register.trace)]
        return [self._load_trace_info(trace) for trace in traces_path]

    def _get_aggregation_info(self):
        path = self.parameters.cache_info_path
        _aggregations = os.listdir(path)
        if _aggregations == []:
            return []
        aggregations_path = [os.path.join(
            path, aggregation) for aggregation in _aggregations if aggregation.startswith(constant.register.aggregation)]
        return [self._load_aggregation_info(aggregation) for aggregation in aggregations_path]

    def print_trace(self, trace):
        print(trace)

    def print_aggregation(self, aggregation):
        print(aggregation)

    def print_traces(self):
        self._header = '='*10 + " Traces " + '='*10 + "\n"
        print(self._header)
        for trace in self._trace_info:
            self.print_trace(trace)

    def print_aggregations(self):
        self._header = '='*10 + " Aggregation " + '='*10 + "\n"
        print(self._header)
        for aggregation in self._aggregation_info:
            self.print_aggregation(aggregation)

    def print(self):
        if self.args.trace:
            self.print_traces()

        if self.args.aggregation:
            self.print_aggregations()
            return

        self.print_traces()
        self.print_aggregations()


register = PytracerInfoRegister()
