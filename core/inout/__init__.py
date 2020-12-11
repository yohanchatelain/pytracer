import os

from pytracer.core.utils.log import get_logger
from pytracer.core.config import constant

from . import _inout

logger = get_logger()

__all__ = ["IO", "IOType", "IOInitializer",
           "reader", "writer", "split_filename",
           "wrapper", "wrapper_class", "wrapper_instance",
           "exporter", "wrapper_ufunc"]


def __getattr__(attr):
    if attr in __all__:
        return _inout.__dict__[attr]
    raise AttributeError


def writer():
    from . import json, pickle, text
    wrapper = None
    init = _inout.IOInitializer()
    if init.get_type() == _inout.IOType.TEXT:
        wrapper = text.Writer().wrapper
    elif init.get_type() == _inout.IOType.JSON:
        wrapper = json.Writer().wrapper
    elif init.get_type() == _inout.IOType.PICKLE:
        wrapper = pickle.Writer().wrapper
    else:
        logger.error(f"Unknown type: {init.get_type()}", _inout.IOTypeError)
    return wrapper


def writer_class():
    from . import json, pickle, text
    wrapper = None
    init = _inout.IOInitializer()
    if init.get_type() == _inout.IOType.TEXT:
        wrapper = text.Writer().wrapper_class
    elif init.get_type() == _inout.IOType.JSON:
        wrapper = json.Writer().wrapper_class
    elif init.get_type() == _inout.IOType.PICKLE:
        wrapper = pickle.Writer().wrapper_class
    else:
        logger.error(f"Unknown type: {init.get_type()}", _inout.IOTypeError)
    return wrapper


def writer_instance():
    from . import json, pickle, text
    wrapper = None
    init = _inout.IOInitializer()
    if init.get_type() == _inout.IOType.TEXT:
        wrapper = text.Writer().wrapper_instance
    elif init.get_type() == _inout.IOType.JSON:
        wrapper = json.Writer().wrapper_instance
    elif init.get_type() == _inout.IOType.PICKLE:
        wrapper = pickle.Writer().wrapper_instance
    else:
        logger.error(f"Unknown type: {init.get_type()}", _inout.IOTypeError)
    return wrapper


def writer_ufunc():
    from . import json, pickle, text
    wrapper = None
    init = _inout.IOInitializer()
    if init.get_type() == _inout.IOType.PICKLE:
        wrapper = pickle.Writer().wrapper_ufunc
    elif True:
        raise NotImplemented
    else:
        logger.error(f"Unknown type: {init.get_type()}", _inout.IOTypeError)
    return wrapper


def reader(iotype):
    from . import json, pickle, text
    _reader = None
    if iotype == _inout.IOType.TEXT:
        _reader = text.Reader()
    elif iotype == _inout.IOType.JSON:
        _reader = json.Reader()
    elif iotype == _inout.IOType.PICKLE:
        _reader = pickle.Reader()
    else:
        logger.error(f"Unknown type: {iotype}")
    return _reader


def exporter():
    from . import pickle
    return pickle.Exporter()


def split_filename(filename):
    from . import json, pickle, text
    function = None
    _, ext = os.path.splitext(filename)
    if ext == constant.text_ext:
        function = text.split_filename(filename)
    elif ext == constant.json_ext:
        function = json.split_filename(filename)
    elif ext == constant.pickle_ext:
        function = pickle.split_filename(filename)
    else:
        raise logger.error(f"Unknown extension {ext}", _inout.IOTypeError)
    return function
