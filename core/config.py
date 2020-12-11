import json
import os
import sys

import pytracer.core.utils as ptutils
from pytracer.core.utils.singleton import Singleton


class PytracerError(Exception):

    def __init__(self, message=None):
        self.message = message


class DictAtKeyError(Exception):

    def __init__(self, key, message=None):
        self.key = key
        self.message = message

    def __getattr__(self, attr):
        if attr in self.__dict__:
            return self.__dict__[attr]
        else:
            return DictAtKeyError(attr)


class NoneDict:

    def __getattr__(self, attr):
        return self

    def __bool__(self):
        return False


class DictAt:
    _attributes = dict().__dir__()

    def __init__(self, _dict):
        _new_dict = dict()
        for key, value in _dict.items():
            new_value = value
            if isinstance(value, dict):
                new_value = DictAt(value)
            _new_dict[key] = new_value
        self._dict = _new_dict

    def __contains__(self, key):
        return key in self._dict

    def __getitem__(self, key):
        return self._dict[key]

    def __getattr__(self, attr):
        if attr in self._attributes:
            return getattr(self._dict, attr, NoneDict())
        if attr in self._dict:
            return self._dict[attr]
        return NoneDict()

    def __repr__(self):
        return repr(self._dict)

    def __str__(self):
        return str(self._dict)


class _Constant(metaclass=Singleton):
    __attributes = {
        "cache": {"root": ".__pytracercache__",
                  "traces": "traces",
                  "stats": "stats"},
        "text_ext": ".txt",
        "json_ext": ".json",
        "pickle_ext": ".pkl",
        "iotypes": ["text", "json", "pickle"],
        "export": {"dat": "stats.pkl",
                   "header": "header.pkl"}

    }

    def __init__(self):
        self.__dict = DictAt(self.__attributes)

    def __getitem__(self, item):
        if item in self.__dict:
            return self.__dict[item]
        else:
            return None

    def __setitem__(self, item, value):
        return NotImplementedError

    def __setattr__(self, attr, value):
        if attr in self.__attributes:
            raise NotImplementedError
        else:
            self.__dict__[attr] = value

    def __getattr__(self, attr):
        if attr in self.__dict:
            return self.__dict[attr]
        else:
            return None


class _Config(object, metaclass=Singleton):

    pytracer_config = "PYTRACER_CONFIG"

    _attributes = ["python_modules_path",
                   "modules_to_load",
                   "include_file",
                   "exclude_file",
                   "logger",
                   "logger.format",
                   "logger.output",
                   "logger.color",
                   "io",
                   "io.type",
                   "io.filename",
                   "io.cache",
                   "io.cache.root",
                   "io.cache.stats",
                   "io.cache.traces",
                   "io.export.dat",
                   "io.export.header",
                   "numpy",
                   "numpy.ufunc"
                   ]

    _data = dict()

    def __init__(self):
        self.read_config()

    def __bool__(self):
        return len(_Config._data()) != 0

    def __getitem__(self, key):
        return NotImplementedError

    def __setitem__(self, key, value):
        return NotImplementedError

    def __getattr__(self, name):
        if name in self._attributes:
            try:
                return getattr(_Config._data, name)
            except KeyError:
                raise DictAtKeyError(name)
        raise KeyError(self.key_error(name))

    def key_error(self, name):
        msg = f"Configuration: Unknown parameter {name}"
        return msg

    def read_config(self):
        config = ptutils.getenv(self.pytracer_config)
        try:
            config_file = open(config)
        except FileNotFoundError as e:
            sys.exit(f"Error while opening file {config}:{os.linesep} {e}")
        _Config._data = DictAt(json.load(config_file))


config = _Config()
constant = _Constant()
