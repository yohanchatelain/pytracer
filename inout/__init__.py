import os

import utils.log
from config import constant

from . import _inout

logger = utils.log.get_log()

__all__ = ["IO", "IOType", "IOInitializer",
           "reader", "writer", "split_filename", "wrapper"]


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


def reader(iotype):
    from . import json, pickle, text
    reader = None
    if iotype == _inout.IOType.TEXT:
        reader = text.Reader()
    elif iotype == _inout.IOType.JSON:
        reader = json.Reader()
    elif iotype == _inout.IOType.PICKLE:
        reader = pickle.Reader()
    else:
        logger.error(f"Unknown type: {iotype}")
    return reader


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
