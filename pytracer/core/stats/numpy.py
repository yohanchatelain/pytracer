import warnings

import numpy as np
import scipy.sparse as spr


def fxn():
    warnings.warn("deprecated", DeprecationWarning)


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    fxn()


class StatisticNumpy:

    __max_sig = {
        np.dtype("bool"): 1,
        np.dtype("uint8"): 8,
        np.dtype("int8"): 8,
        np.dtype("int16"): 16,
        np.dtype("uint16"): 16,
        np.dtype("int32"): 32,
        np.dtype("uint32"): 32,
        np.dtype("int64"): 64,
        np.dtype("uint64"): 64,
        np.dtype("float16"): 11,
        np.dtype("float32"): 24,
        np.dtype("float64"): 53,
        # Warning: float128 in numpy means fp80!
        np.dtype("float128"): 80,
        np.dtype("object"): 0
    }

    def __init__(self, values, empty=False):

        if not empty and values.ndim == 0:
            empty = True

        if empty:
            self.cached_mean = np.nan
            self.cached_sig = np.nan
            self.cached_std = np.nan
            self._data = values
            self._samples = len(values)
            self._size = 1
            self._ndim = 0
            self._shape = ()
        else:
            if isinstance(values, list):
                raise Exception
            self._data = self._preprocess_values(values)
            self._samples = len(values)
            self._size = values.size/self._samples
            self._ndim = self._data.ndim - 1
            self._shape = self._data.shape[1:]
            self._type = self._data.dtype

    def _preprocess_values(self, values):
        x0 = values[0]
        if spr.issparse(x0):
            return np.array([x.toarray() for x in values])
        else:
            return values

    def __getstate__(self):
        to_return = {"mean": self.cached_mean,
                     "std": self.cached_std,
                     "sig": self.cached_sig}
        return to_return

    def __setstate__(self, d):
        self.__dict__.update(d)

    def dtype(self):
        return self._data.dtype

    def ndim(self):
        return self._ndim

    def shape(self):
        return self._shape

    def size(self):
        return self._size

    def mean(self):
        _mean = getattr(self, "cached_mean", None)
        if _mean is None:
            with warnings.catch_warnings():
                # warnings.simplefilter("ignore")
                # if spr.issparse(self._data[0]):
                #     # self._data.reshape(
                #     #     (self._data.shape[0],) + self._data[0].shape)
                #     print("DATA", self._data)
                #     spr.csr_matrix.mean(self._data, axis=0)
                # else:
                try:
                    _mean = np.mean(self._data, axis=0, dtype=np.float64)
                except Exception:
                    _mean = 0.0
        self.cached_mean = _mean
        return _mean

    def std(self):
        _std = getattr(self, "cached_std", None)
        if _std is None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    if spr.issparse(self._data[0]):
                        spr.csr_matrix.std(
                            self._data, axis=0, dtype=np.float64)
                    else:
                        _std = np.std(self._data, axis=0, dtype=np.float64)
                except Exception:
                    _std = 0.0
        self.cached_std = _std
        return _std

    def significant_digits(self):
        return self.sig()

    def sig(self):
        _sig = getattr(self, "cached_sig", None)
        if _sig is None:
            _mean = self.mean()
            _std = self.std()
            _sig = self._sig(_mean, _std)
            self.cached_sig = _sig
        return _sig

    def _sig(self, mean, std):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if not spr.issparse(mean):
                masked_std = np.ma.masked_equal(std, 0.0)
                masked_mean = np.ma.masked_equal(mean, 0.0)
                sig = np.log2(np.abs(masked_mean/masked_std))
                if hasattr(sig, "filled"):
                    if self._type.kind in ('U', 'S'):
                        sig = sig.filled(8)
                    else:
                        sig = sig.filled(self.__max_sig[self._type])

            else:
                sig = np.log2(np.abs(mean/std))
        return sig

    @staticmethod
    def hasinstance(obj):
        if isinstance(obj, type):
            return False

        if not hasattr(obj, "dtype"):
            return False

        if getattr(obj, "size", -1) == 0:
            return False

        return np.issubdtype(obj.dtype, np.number) or np.issubdtype(obj.dtype, np.bool_)
