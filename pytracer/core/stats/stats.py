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


_type_cache = set()


def get_type(value):
    from pytracer.core.stats.numpy import StatisticNumpy
    from pytracer.core.stats.sklearn import is_sklearn_value
    import numpy as np
    _type = None
    if isinstance(value, bool):
        _type = TypeValue.BOOL
    elif isinstance(value, int):
        _type = TypeValue.INT
    elif isinstance(value, float):
        _type = TypeValue.FLOAT
    elif StatisticNumpy.hasinstance(value):
        _type = TypeValue.NUMPY
    elif isinstance(value, list):
        try:
            array = np.array(value, dtype=np.object)
            if StatisticNumpy.hasinstance(array):
                _type = TypeValue.LIST
            else:
                _type = TypeValue.OTHER
        except ValueError:
            array = tuple(value)
            _type = TypeValue.TUPLE
    elif isinstance(value, tuple):
        _type = TypeValue.TUPLE
    elif isinstance(value, FunctionType):
        _type = TypeValue.FUNCTION
    elif is_sklearn_value(value):
        _type = TypeValue.SKLEARN
    else:
        _type = TypeValue.OTHER
        # if not isinstance(value, (str, np.ndarray, np.dtype, type)):
        #     if type(value) not in _type_cache:
        #         logger.warning(f"Unknown type: {type(value)} {value}")
        #         _type_cache.add(type(value))
    return _type


def check_type(values):
    types = [*map(type, values)]
    # Ensure that values have all the same type
    assert(len(set(types)) == 1)


def get_stats(values):
    from pytracer.core.stats.numpy import StatisticNumpy
    from pytracer.core.stats.sklearn import get_sklearn_stat
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
        array = np.array(values)
        _stats = StatisticNumpy(array)
    elif _type == TypeValue.TUPLE:
        types = [*map(get_type, values[0])]
        _stats = []
        zipv = zip(*values)
        [(t, v) for t, v in zip(types, zipv)]
        append = _stats.append
        for ty, v in zip(types, zipv):
            if ty == TypeValue.OTHER:
                append(StatisticNumpy(v, empty=True))
            else:
                append(StatisticNumpy(np.array(v)))
    elif _type == TypeValue.NUMPY:
        try:
            array = np.array(values)
            _stats = StatisticNumpy(array)
        except:
            logger.debug(f"Cannot parse {values}")
            _stats = StatisticNumpy(values, empty=True)
    elif _type == TypeValue.SKLEARN:
        _stats = get_sklearn_stat(values, type(values[0]))
    else:
        _stats = get_stat(np.array(values))

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
