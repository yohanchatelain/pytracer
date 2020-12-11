from enum import IntEnum, auto
from types import FunctionType

import numpy as np

from core.utils.log import get_logger
from core.stats.numpy import StatisticNumpy

logger = get_logger()

types = (StatisticNumpy,)


class TypeValue(IntEnum):
    INT = auto()
    FLOAT = auto()
    NUMPY = auto()
    LIST = auto()
    TUPLE = auto()
    FUNCTION = auto()
    OTHER = auto()

    def is_scalar(self):
        if not hasattr(self, "__scalar"):
            self.__scalar = (self.INT,
                             self.FLOAT)
        return self in self.__scalar

    def is_vector(self):
        if not hasattr(self, "__vector"):
            self.__vector = (self.VECTOR,)
        return self in self.__vector

    def is_matrix(self):
        if not hasattr(self, "__matrix"):
            self.__matrix = (self.MATRIX,)
        return self in self.__matrix

    def is_function(self):
        if not hasattr(self, "__function"):
            self.__function = (self.FUNCTION,)
        return self in self.__function

    def is_other(self):
        if not hasattr(self, "__other"):
            self.__other = (self.OTHER,)
        return self in self.__other

    def is_numeric(self):
        return not self.is_function() and not self.is_other()


def get_type(value):
    _type = None
    if isinstance(value, int):
        _type = TypeValue.INT
    elif isinstance(value, float):
        _type = TypeValue.FLOAT
    elif StatisticNumpy.hasinstance(value):
        _type = TypeValue.NUMPY
    elif isinstance(value, list):
        array = np.array(value)
        if StatisticNumpy.hasinstance(array):
            _type = TypeValue.LIST
        else:
            _type = TypeValue.OTHER
    elif isinstance(value, tuple):
        _type = TypeValue.TUPLE
    elif isinstance(value, FunctionType):
        _type = TypeValue.FUNCTION
    else:
        _type = TypeValue.OTHER
        if not isinstance(value, (str, np.ndarray, np.dtype, type)):
            logger.warning(f"Unknown type: {type(value)} {value}")
    return _type


def check_type(values):
    types = [type(value) for value in values]
    # Ensure that values have all the same type
    assert(len(set(types)) == 1)


def get_stats(values):
    check_type(values)
    _type = get_type(values[0])
    _stats = None
    if _type == TypeValue.INT:
        array = np.array(values, dtype=np.int64)
        _stats = StatisticNumpy(array)
    elif _type == TypeValue.FLOAT:
        array = np.array(values, dtype=np.float64)
        _stats = StatisticNumpy(array)
    elif _type == TypeValue.LIST:
        array = np.array(values)
        _stats = StatisticNumpy(array)
    elif _type == TypeValue.TUPLE:
        types = [get_type(t) for t in values[0]]
        _stats = []
        zipv = zip(*values)
        [(t, v) for t, v in zip(types, zipv)]
        for ty, v in zip(types, zipv):
            if ty == TypeValue.OTHER:
                _stats.append(StatisticNumpy(v, empty=True))
            else:
                _stats.append(StatisticNumpy(np.array(v)))
    elif _type == TypeValue.NUMPY:
        array = np.array(values)
        _stats = StatisticNumpy(array)
    else:
        _stats = StatisticNumpy(values, empty=True)
        # _stats = values[0]

    return _stats


def tohex(value):
    try:
        v = float(value)
        return hex(v)
    except TypeError:
        try:
            v = [tohex(v) for v in value]
            return v
        except TypeError:
            return value


def print_stats(arg, stat):
    logger.debug(f"\tArg {arg}")
    if isinstance(stat, types):
        logger.debug(f"\tNumber of elements: {stat.size()}")
        logger.debug(f"\t\tmean: {stat.mean()}")
        logger.debug(f"\t\t std: {stat.std()}")
        logger.debug(f"\t\t sig: {stat.significant_digits()}")
    else:
        logger.debug(f"\t\tNo stats provided for {stat}")
