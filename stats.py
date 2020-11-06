from logging import Logger
import numpy as np
import math
import statistics as stat
from enum import IntEnum, auto

from numpy.lib.arraysetops import isin
import utils.log
import os

logger = utils.log.get_log()


class TypeValue(IntEnum):
    INT = auto()
    FLOAT16 = auto()
    FLOAT32 = auto()
    FLOAT64 = auto()
    FLOAT128 = auto()
    VECTOR = auto()
    MATRIX = auto()
    TENSOR = auto()
    OTHER = auto()

    def is_scalar(self):
        if not hasattr(self, "__scalar"):
            self.__scalar = (self.INT,
                             self.FLOAT16, self.FLOAT32,
                             self.FLOAT64, self.FLOAT128)
        return self in self.__scalar

    def is_vector(self):
        if not hasattr(self, "__vector"):
            self.__vector = (self.VECTOR,)
        return self in self.__vector


class Statistic:

    __max_sig = {
        TypeValue.INT: 64,
        TypeValue.FLOAT16: 11,
        TypeValue.FLOAT32: 24,
        TypeValue.FLOAT64: 53,
        TypeValue.FLOAT128: 112
    }

    def __init__(self, values):
        self.check_type(values)
        self._data = values

    @staticmethod
    def get_type(value):
        if isinstance(value, int):
            return TypeValue.INT
        if isinstance(value, float):
            return TypeValue.FLOAT64
        if isinstance(value, np.float16):
            return TypeValue.FLOAT16
        if isinstance(value, np.float32):
            return TypeValue.FLOAT32
        if isinstance(value, np.float64):
            return TypeValue.FLOAT64
        if isinstance(value, np.float128):
            return TypeValue.FLOAT128
        if isinstance(value, np.ndarray):
            if value.ndim == 1:
                return TypeValue.VECTOR
            elif value.ndim == 2:
                return TypeValue.MATRIX
            else:
                return TypeValue.TENSOR
        logger.warning(f"Unknown type: {type(value)} for {value}")
        return TypeValue.OTHER

    def check_type(self, values):
        types = [type(value) for value in values]
        # Ensure that values have all the same type
        assert(len(set(types)) == 1)
        value = values[0]
        self.type = self.get_type(value)

    def mean(self):
        if hasattr(self, "cached_mean"):
            return self.cached_mean
        self.cached_mean = self.__mean(self._data)
        return self.cached_mean

    def __mean(self, data):
        if self.type.is_scalar():
            return stat.mean(data)
        if self.type.is_vector():
            return np.mean(data, axis=0)
        raise NotImplementedError

    def std(self):
        if hasattr(self, "cached_std"):
            return self.cached_std
        self.cached_std = self.__std(self._data)
        return self.cached_std

    def __std(self, data):
        if self.type.is_scalar():
            return stat.stdev(data)
        if self.type.is_vector():
            return np.std(data, axis=0)
        raise NotImplementedError

    def significant_digits(self):
        if hasattr(self, "cached_sig"):
            return self.cached_sig
        self.cached_sig = self.__significant_digits(self._data)
        return self.cached_sig

    def __significant_digits(self, data):
        mean = self.__mean(data)
        std = self.__std(data)
        if self.type.is_scalar():
            return self.__scalar_significant_digits(mean, std)
        if self.type.is_vector():
            return self.__vector_significant_digits(mean, std)
        raise NotImplementedError

    def __scalar_significant_digits(self, mean, std):
        if mean == 0.0 and std == 0.0:
            return self.__max_sig[self.type]
        if mean == 0.0:
            return -math.log2(abs(std))
        if std == 0.0:
            return self.__max_sig[self.type]
        return -math.log2(abs(std/mean))

    def __vector_significant_digits(self, mean, std):
        v = np.vectorize(self.__scalar_significant_digits)
        return v(mean, std)

    def __repr__(self):
        mean = self.__mean(self._data)
        std = self.__std(self._data)
        sig = self.__significant_digits(self._data)
        msg = (f"mean: {mean},"
               f"std: {std},"
               f"s: {sig}")
        return msg
