import warnings

import numpy as np
import scipy.sparse as spr


warnings.simplefilter('ignore')


class StatisticNumpy:

    __max_sig = {
        int: 64,
        float: 53,
        complex: 53,
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
        np.dtype("float128"): np.finfo(np.dtype('float128')).nmant+1,
        np.dtype("complex64"): 24,
        np.dtype("complex128"): 53,
        np.dtype("complex256"): np.finfo(np.dtype('complex256')).nmant+124,
        np.dtype("object"): 53
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
            self._type = np.object_
        else:
            if isinstance(values, list):
                raise Exception
            self._data = self._preprocess_values(values)
            self._samples = len(values)
            self._size = values.size/self._samples
            self._ndim = self._data.ndim - 1
            self._shape = self._data.shape[1:]
            self._type = self._data.dtype

        if not (np.issubdtype(self._type, np.number) or np.issubdtype(self._type, np.bool_)):
            self.cached_mean = np.nan
            self.cached_std = np.nan
            self.cached_sig = np.nan

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

    def _mean_sparse(self):
        return np.sum(self._data[0])/self._samples

    def _std_sparse(self, _mean):
        return np.sum([(m - _mean).power(2) / self._samples for m in self._data]).sqrt()

    def _mean(self, data):
        return np.mean(data, axis=0, dtype=np.float64)

    def mean(self):
        _mean = getattr(self, "cached_mean", None)
        if _mean is None:
            if spr.issparse(self._data[0]):
                _mean = self._mean_sparse()
            elif np.iscomplexobj(self._data):
                _mean_real = self._mean(self._data.real)
                _mean_imag = self._mean(self._data.imag)
                _mean = _mean_real + 1j * _mean_imag
            else:
                _mean = self._mean(self._data)
        self.cached_mean = _mean
        return _mean

    def _std(self, data):
        return np.std(data, axis=0, dtype=np.float64)

    def std(self):
        _std = getattr(self, "cached_std", None)
        if _std is None:
            if spr.issparse(self._data[0]):
                _std = self._std_sparse()
            elif np.iscomplexobj(self._data):
                _std_real = self._std(self._data.real)
                _std_imag = self._std(self._data.imag)
                _std = _std_real + 1j * _std_imag
            else:
                _std = self._std(self._data)
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

    def _sig_part(self, mean, std):
        if not spr.issparse(mean):
            masked_std = np.ma.masked_equal(std, 0.0)
            masked_mean = np.ma.masked_equal(mean, 0.0)
            sig = np.log2(np.abs(masked_mean/masked_std))
            if hasattr(sig, "filled"):
                if self._type.kind in ('U', 'S'):
                    sig = sig.filled(8)
                else:
                    sig[masked_mean.mask] = 0
                    sig[masked_std.mask] = self.__max_sig.get(self._type, 53)
                    sig = sig.data
        else:
            sig = np.log2(np.abs(mean/std))
        return sig

    def _sig(self, mean, std):
        if np.iscomplexobj(self._data):
            _sig_real = self._sig_part(mean.real, std.real)
            _sig_imag = self._sig_part(mean.imag, std.imag)
            _sig = _sig_real + 1j * _sig_imag
        else:
            _sig = self._sig_part(mean, std)
        return _sig

    @staticmethod
    def hasinstance(obj):
        if isinstance(obj, type):
            return False

        if not hasattr(obj, "dtype"):
            return False

        if getattr(obj, "size", -1) == 0:
            return False

        return np.issubdtype(obj.dtype, np.number) or np.issubdtype(obj.dtype, np.bool_)
