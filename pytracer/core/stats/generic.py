from pytracer.core.stats.numpy import StatisticNumpy

import numpy as np
import types
import inspect

builtin_types = (bool, str,  dict, type(
    None), types.FunctionType, types.ModuleType, types.MethodType,
    types.MappingProxyType, types.BuiltinFunctionType, types.BuiltinMethodType,
    types.AsyncGeneratorType, frozenset, np.dtype, type)


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
            return StatisticNumpy(np.array(values))

    for attr in dir(x0):
        try:
            attr_value = getattr(x0, attr, None)
        except Exception:
            continue
        if is_valid_attribute(attr_value):
            if attr_value is not None:
                try:
                    xarray = np.array([getattr(x, attr) for x in values])
                    empty = False
                except ValueError:
                    try:
                        array_list = [getattr(x, attr) for x in values]
                        flat_list = [
                            item for sublist in array_list for item in sublist]
                        xarray = np.array(flat_list)
                        empty = False
                    except Exception:
                        xarray = np.array([])
                        empty = True
                except Exception:
                    xarray = np.array([])
                    empty = True
                _data[attr] = StatisticNumpy(xarray, empty=empty)

    return _data
