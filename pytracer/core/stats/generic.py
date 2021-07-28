from pytracer.core.stats.numpy import StatisticNumpy

import numpy as np
import types
import inspect

builtin_types = (bool, list, str,  dict, type(
    None), types.FunctionType, types.ModuleType, types.MethodType,
    types.MappingProxyType, types.BuiltinFunctionType, types.BuiltinMethodType,
    types.AsyncGeneratorType, frozenset, np.dtype)


def is_function(value):
    return inspect.isfunction(value) or \
        inspect.ismethod(value) or \
        inspect.isabstract(value) or \
        inspect.isasyncgenfunction(value) or \
        inspect.isdatadescriptor(value) or \
        inspect.ismemberdescriptor(value) or \
        inspect.iscoroutinefunction(value) or \
        inspect.isgetsetdescriptor(value) or \
        inspect.ismethoddescriptor(value)


def is_valid_attribute(value):
    return type(value) not in builtin_types and not callable(value) and not is_function(value)


def get_stat(values):
    _data = {}
    x0 = values[0]
    _type = type(x0)
    if _type in builtin_types:
        return StatisticNumpy(values, empty=True)

    if isinstance(x0, np.ndarray):
        if 0 in x0.shape:
            return StatisticNumpy(values, empty=True)
        else:
            return StatisticNumpy(values)

    print(f"Generic parser for type {type(x0)}")
    print(values)
    for attr in dir(x0):
        attr_value = getattr(x0, attr, None)
        if is_valid_attribute(attr_value):
            print("Attribute", attr)
            if attr_value is not None:
                _data[attr] = StatisticNumpy(
                    np.array([getattr(x, attr) for x in values]))
    return _data
