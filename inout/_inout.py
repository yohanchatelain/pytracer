import os
from enum import IntEnum, auto

import utils
import utils.log
from config import DictAtKeyError
from config import config as cfg
from config import constant
from utils.singleton import Singleton


logger = utils.log.get_log()


class IOType(IntEnum):
    TEXT = auto()
    JSON = auto()
    PICKLE = auto()


class IOTypeError(Exception):
    def __init__(self, msg=""):
        self.msg = msg


class IOInitializer(metaclass=Singleton):

    parameters = dict()
    cache_default = constant.cache
    type_default = IOType.PICKLE
    filename_default = None

    def __init__(self):
        self.read_parameters()
        self.mkdir_cache()

    def mkdir_cache(self):
        self.cache_path = f"{os.getcwd()}{os.sep}{self.cache}"
        if not os.path.isdir(self.cache_path):
            os.makedirs(self.cache_path)

    def get_type(self):
        return self.type

    def read_parameters(self):
        try:
            self.type = cfg.io.type
        except DictAtKeyError:
            self.type = self.type_default
        try:
            self.cache = cfg.io.cache
        except DictAtKeyError:
            self.cache = self.cache_default
        try:
            self.filename = cfg.io.filename
        except DictAtKeyError:
            self.filename = self.filename_default


def wrapper(self, function, *args, **kwargs):
    try:
        nb_args = function.__code__.co_argcount
        argsnames = function.__code__.co_varnames[:nb_args]
        inputs = {**dict(zip(argsnames, args)), **kwargs}
    except AttributeError:
        inputs = {**{f"x{i}": x for i, x in enumerate(args)}, **kwargs}

    self.inputs(function, inputs)
    outputs = function(*args, **kwargs)
    self.outputs(function, outputs)
    return outputs
