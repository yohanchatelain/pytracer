from enum import IntEnum, auto
from types import FunctionType

from pytracer.utils.log import get_logger

logger = get_logger()


class TypeValue(IntEnum):
    INT = auto()
    FLOAT = auto()
    NUMPY = auto()
    BOOL = auto()
    LIST = auto()
    TUPLE = auto()
    FUNCTION = auto()
    SKLEARN = auto()
    STRING = auto()
    OTHER = auto()

    def is_scalar(self):
        if not hasattr(self, "__scalar"):
            self.__scalar = (self.BOOL,
                             self.INT,
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
    from pytracer.core.stats.numpy import StatisticNumpy
    import numpy as np
    _type = None
    if isinstance(value, bool):
        _type = TypeValue.BOOL
    elif isinstance(value, int):
        _type = TypeValue.INT
    elif isinstance(value, float):
        _type = TypeValue.FLOAT
    elif StatisticNumpy.hasinstance(value) or isinstance(value, np.ndarray):
        _type = TypeValue.NUMPY
    elif isinstance(value, list):
        try:
            array = np.array(value, dtype=np.float64)
            if StatisticNumpy.hasinstance(array):
                _type = TypeValue.LIST
            else:
                _type = TypeValue.OTHER
        except (ValueError, TypeError):
            array = tuple(value)
            _type = TypeValue.TUPLE
    elif isinstance(value, tuple):
        _type = TypeValue.TUPLE
    elif isinstance(value, FunctionType):
        _type = TypeValue.FUNCTION
    else:
        _type = TypeValue.OTHER
    return _type


def check_type(values):
    types = [*map(type, values)]
    # Ensure that values have all the same type
    if len(set(types)) != 1:
        logger.error('Parsed values do not have the same type: {set(types)}')


def get_stats(values):
    from pytracer.core.stats.numpy import StatisticNumpy
    from pytracer.core.stats.generic import get_stat
    import numpy as np
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
        try:
            array = np.concatenate(values)
        except ValueError as e:
            logger.error(
                f'Array length mismatch between samples {values}', error=e)
        _stats = StatisticNumpy(array)
    elif _type == TypeValue.TUPLE:
        types = [*map(get_type, values[0])]
        _stats = []
        zipv = zip(*values)
        [(t, v) for t, v in zip(types, zipv)]
        append = _stats.append
        for ty, v in zip(types, zipv):
            if ty == TypeValue.OTHER:
                append(get_stat(np.array(v, dtype=np.object)))
            else:
                append(StatisticNumpy(np.array(v)))
    elif _type == TypeValue.NUMPY:
        try:
            array = np.array(values)
            _stats = StatisticNumpy(array)
        except Exception:
            logger.debug(f"Cannot parse {values}")
            _stats = StatisticNumpy(values, empty=True)
    elif _type == TypeValue.STRING:
        _stats = StatisticNumpy(values, empty=True, dtype=type(values[0]))
    else:
        _stats = get_stat(np.array(values, dtype=np.object))

    return _stats


def tohex(value):
    try:
        v = float(value)
        return hex(v)
    except TypeError:
        try:
            v = [*map(tohex, value)]
            return v
        except TypeError:
            return value


def print_stats(arg, stat):
    from pytracer.core.stats.numpy import StatisticNumpy
    types = (StatisticNumpy,)
    logger.debug(f"\tArg {arg}")
    if isinstance(stat, types):
        logger.debug(f"\tNumber of elements: {stat.size()}")
        logger.debug(f"\t\tmean: {stat.mean()}")
        logger.debug(f"\t\t std: {stat.std()}")
        logger.debug(f"\t\t sig: {stat.significant_digits()}")
    else:
        logger.debug(f"\t\tNo stats provided for {stat}")
