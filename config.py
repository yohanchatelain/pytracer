import json
import os
import sys

import utils
import utils.singleton


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
            return self._dict.__getattr__(attr)
        if attr in self._dict:
            return self._dict[attr]
        return None


class _Constant(metaclass=utils.singleton.Singleton):
    __attributes = {
        "cache": ".__pytracer_cache__",
        "text_ext": ".txt",
        "json_ext": ".json",
        "pickle_ext": ".pkl",
        "iotypes": ["text", "json", "pickle"]
    }

    def __getitem__(self, item):
        if item in self.__attributes:
            return self.__attributes[item]
        else:
            raise KeyError

    def __setitem__(self, item, value):
        return NotImplementedError

    def __setattr__(self, attr, value):
        if attr in self.__attributes:
            raise NotImplementedError
        else:
            self.__dict__[attr] = value

    def __getattr__(self, attr):
        if attr in self.__attributes:
            return self.__attributes[attr]
        else:
            return self.__dict__[attr]


class _Config(metaclass=utils.singleton.Singleton):

    pytracer_config = "PYTRACER_CONFIG"

    _attributes = ["modules_to_load",
                   "include_file",
                   "exclude_file",
                   "logger",
                   "logger.format",
                   "logger.output",
                   "logger.color",
                   "io",
                   "io.cache",
                   "io.type",
                   "io.filename"
                   ]

    def __init__(self):
        self._data = dict()
        self.read_config()

    def __bool__(self):
        return len(self._data()) != 0

    def __getitem__(self, key):
        return NotImplementedError

    def __setitem__(self, key, value):
        return NotImplementedError

    def __getattr__(self, name):
        if name in self._attributes:
            try:
                return self._data[name]
            except KeyError:
                raise DictAtKeyError(name)
        raise KeyError(self.key_error(name))

    def key_error(self, name):
        msg = f"Configuration: Unknown parameter {name}"
        return msg

    def read_config(self):
        config = utils.getenv(self.pytracer_config)
        try:
            config_file = open(config)
        except FileNotFoundError as e:
            sys.exit(f"Error while opening file {config}:{os.linesep} {e}")
        self._data = DictAt(json.load(config_file))


config = _Config()
constant = _Constant()
