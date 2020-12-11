from inspect import Traceback
import os
from enum import IntEnum, auto

from pytracer.core.utils.log import get_logger
from pytracer.core.config import constant, config as cfg
from pytracer.core.utils.singleton import Singleton
import numpy as np

logger = get_logger()


class Counter(metaclass=Singleton):

    def __init__(self):
        self._internal = 0

    def increment(self):
        self._internal += 1

    def __call__(self):
        return self._internal


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


class IOTypeError(Exception):
    def __init__(self, msg=""):
        self.msg = msg


class IOInitializer(metaclass=Singleton):

    parameters = dict()
    type_default = IOType.PICKLE
    filename_default = None
    cache_default = {"root": constant.cache.root,
                     "traces": constant.cache.traces,
                     "stats": constant.cache.stats}
    export_default = constant.export

    def __init__(self):
        self.read_parameters()
        self.mkdir_cache()

    def _get_parameters(self, param, default):
        if param:
            return param
        else:
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
            logger.debug(f"cache directory created {self.cache_traces_path}")

        self.cache_stats_path = f"{self.cache_path}{os.sep}{self.cache_stats}"
        if not os.path.isdir(self.cache_stats_path):
            os.makedirs(self.cache_stats_path)
            logger.debug(f"cache directory created {self.cache_stats_path}")

    def get_type(self):
        return self.type


elements = Counter()


def wrapper(self, info, *args, **kwargs):
    from pytracer.core.wrapper.wrapper import Wrapper

    function_id, function_module, function_name = info
    function = Wrapper.id_dict[function_id]
    info = (function_module, function_name)

    inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}
    stack = self.backtrace()

    if hasattr(function, "__pytracer__"):
        logger.error(f"Function {function} is wrapped itself")

    time = elements()
    self.inputs(time=time,
                module_name=function_module,
                function_name=function_name,
                function=function,
                args=inputs,
                backtrace=stack)
    outputs = function(*args, **kwargs)

    if not isinstance(outputs, dict):
        _outputs = {"x0": outputs}
    else:
        _outputs = outputs
    self.outputs(time=time,
                 module_name=function_module,
                 function_name=function_name,
                 function=function,
                 args=_outputs,
                 backtrace=stack)
    # self.outputs(time, info, function, outputs)
    elements.increment()
    return outputs


def wrapper_instance(self, function, instance, *args, **kwargs):

    inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}
    stack = self.backtrace()

    time = elements()
    self.inputs_instance(time=time,
                         instance=function,
                         args=inputs,
                         backtrace=stack)
    # self.inputs_instance(time=time, instance=instance, args=inputs)
    outputs = function(instance, *args, **kwargs)
    if not isinstance(outputs, dict):
        _outputs = {"x0": outputs}
    else:
        _outputs = outputs

    self.outputs_instance(time=time,
                          instance=function,
                          args=_outputs,
                          backtrace=stack)
    # self.outputs_instance(time, instance, outputs)
    elements.increment()
    return outputs


def get_inputs_type(inputs):
    inputs_type = list()

    for input_ in inputs:
        if np.isscalar(input_):
            inputs_type.append(np.dtype(type(input_)))
        elif np.issubdtype(input_, np.ndarray):
            inputs_type.append(input_.dtype)
        else:
            inputs_type.append(np.ndarray(input_).dtype)

    return inputs_type


def get_ufunc_output_type(args_type, sig_types):

    inputs_sym = "".join([arg_type.char for arg_type in args_type])
    for sig_type in sig_types:
        if sig_type.startswith(inputs_sym):
            return sig_type[sig_type.find("->")+2:]

    # The inputs types are not in the signatures of the function
    # We need to find a safe casting
    for sig_type in sig_types:
        return_pos = sig_type.find("->")
        input_type = sig_type[:return_pos]
        output_type = sig_type[return_pos+2:]

        casted_inputs_type = ""
        for i, ity in enumerate(input_type):
            casted_inputs_type = ""
            if np.can_cast(inputs_sym[i], ity):
                casted_inputs_type += ity
            else:
                casted_inputs_type = ""
                break

        if casted_inputs_type != "":
            logger.debug(
                f"Find casting rule {casted_inputs_type} for {inputs_sym}")
            return output_type

    logger.error(
        f"Cannot find suitable casting rule for {args_type} {sig_types}")

    return None


def wrapper_ufunc(self, function, *args, **kwargs):

    inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}
    stack = self.backtrace()

    time = elements()
    self.inputs_instance(time=time,
                         instance=function,
                         args=inputs,
                         backtrace=stack)
    outputs = function(*args, **kwargs)
    inputs_type = None
    outputs_type = None
    if args:
        inputs_type = get_inputs_type(args)
        outputs_type = get_ufunc_output_type(inputs_type, function.types)
        outputs = outputs.astype(outputs_type)

    if not isinstance(outputs, dict):
        _outputs = {"x0": outputs}
    else:
        _outputs = outputs

    self.outputs_instance(time=time,
                          instance=function,
                          args=_outputs,
                          backtrace=stack)
    elements.increment()
    return outputs


def wrapper_instance(self, instance, *args, **kwargs):

    inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}
    stack = self.backtrace()

    time = elements()
    self.inputs_instance(time=time,
                         instance=instance,
                         args=inputs,
                         backtrace=stack)
    outputs = instance.function(*args, **kwargs)
    if not isinstance(outputs, dict):
        _outputs = {"x0": outputs}
    else:
        _outputs = outputs

    self.outputs_instance(time=time,
                          instance=instance,
                          args=_outputs,
                          backtrace=stack)
    # self.outputs_instance(time, instance, outputs)
    elements.increment()
    return outputs


def wrapper_class(self, function_id, *args, **kwargs):
    from pytracer.core.wrapper.wrapper import Wrapper

    function = Wrapper.id_dict[function_id]

    inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}
    stack = self.backtrace()

    time = elements()
    self.inputs(time=time, function=function, args=inputs, backtrace=stack)
    outputs = function(*args, **kwargs)
    if not isinstance(outputs, dict):
        _outputs = {"x0": outputs}
    else:
        _outputs = outputs
    self.outputs(time=time, function=function, args=_outputs, backtrace=stack)
    elements.increment()
    return outputs
