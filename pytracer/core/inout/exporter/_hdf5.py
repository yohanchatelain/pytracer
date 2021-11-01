import atexit
import os
import warnings
from collections import namedtuple

import numpy as np
import pytracer.utils as ptutils
import tables
from pytracer.core.config import constant
from pytracer.utils.log import get_logger
import scipy.sparse as spr
from time import perf_counter

from . import _exporter, _init

warnings.simplefilter('ignore')

logger = get_logger()

BacktraceDict = namedtuple(typename="BacktraceDict",
                           field_names=["filename",
                                        "line",
                                        "lineno",
                                        "locals",
                                        "name"])


class ExportDescription(tables.IsDescription):
    id = tables.UInt64Col()
    label = tables.StringCol(16)
    name = tables.StringCol(128)
    time = tables.UInt64Col()
    mean = tables.Float64Col()
    std = tables.Float64Col()
    sig = tables.Float64Col()
    info = tables.StringCol(256)
    dtype = tables.StringCol(256)

    class BacktraceDescription(tables.IsDescription):
        filename = tables.StringCol(1024)
        line = tables.StringCol(1024)
        lineno = tables.IntCol()
        name = tables.StringCol(128)


_id_to_times = dict()


class ExporterHDF5(_exporter.Exporter):

    count_ofile = 0
    group_id = dict()

    def _get_path(self, path):
        if path not in ExporterHDF5.group_id:
            ExporterHDF5.group_id[path] = 0
            _path = f"{path};{ExporterHDF5.group_id[path]}"
        else:
            _path = f"{path};{ExporterHDF5.group_id[path]}"
            node = self.h5file.get_node(_path)

            if len(node._v_groups) >= node._v_max_group_width:
                ExporterHDF5.group_id[path] += 1
                _path = f"{path};{ExporterHDF5.group_id[path]}"

        return _path

    def __init__(self):
        self.parameters = _init.IOInitializer()
        self._init_ostream()
        atexit.register(self.end)

    def get_filename(self):
        return self.filename

    def get_filename_path(self):
        return self.filename_path

    def _init_ostream(self):
        filename = self.parameters.export
        self.filename = ptutils.get_filename(
            filename, ext=constant.extension.hdf5)
        self.filename_path = self._get_filename_path(self.filename)
        self.h5file = tables.open_file(self.filename_path, mode="w")

    def _get_filename_path(self, filename):
        ptutils.check_extension(filename, constant.extension.hdf5)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.extension.hdf5
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{self.parameters.cache_stats}{os.sep}"
                f"{filename}{ext}")

    def end(self):
        self.h5file.close()

    def backtrace_to_dict(self, backtrace):
        return BacktraceDict(filename=backtrace.filename,
                             line=backtrace.line,
                             lineno=backtrace.lineno,
                             name=backtrace.name)

    def _register_obj(self, obj):
        try:
            function_id = obj["id"]
            if function_id in _id_to_times:
                time = obj["time"]
                backtrace = self.backtrace_to_dict(obj["backtrace"])
                bt_to_time = _id_to_times[function_id]["backtrace"]
                if backtrace in bt_to_time:
                    bt_to_time[backtrace].add(time)
                else:
                    bt_to_time[backtrace] = set([time])
            else:
                backtrace = self.backtrace_to_dict(obj["backtrace"])
                bt_to_time = {backtrace: set([obj["time"]])}
                new_registration = {"name": obj["function"],
                                    "module": obj["module"],
                                    "backtrace": bt_to_time}
                _id_to_times[function_id] = new_registration
        except Exception as e:
            logger.error(
                f"Cannot registered object {obj}", error=e, caller=self)

    def _get_sparse_representation_shape(self, sparse_array):
        csr = sparse_array.tocsr()
        data_size = csr.data.size
        indices_size = csr.indices.size
        indptr_size = csr.indptr.size
        _sizes = [1, data_size, 1, indices_size, 1, indptr_size]
        return (sum(_sizes),)

    def _get_sparse_representation(self, sparse_array):
        csr = sparse_array.tocsr()
        data_size = csr.data.size
        indices_size = csr.indices.size
        indptr_size = csr.indptr.size
        _sizes = [1, data_size, 1, indices_size, 1, indptr_size]
        _size = sum(_sizes)
        _size_i = 0
        _index_start = 0
        _index_end = _sizes[_size_i]

        pytracer_type = np.dtype([('Pytracer', csr.dtype)])
        _sparse = np.empty(_size, pytracer_type)

        _sparse[_index_start:_index_end] = data_size
        _size_i += 1
        _index_start_ = _index_start
        _index_start = _index_end
        _index_end += _sizes[_size_i] + _index_start_

        _sparse[_index_start: _index_end] = csr.data
        _size_i += 1
        _index_start = _index_end
        _index_end += _sizes[_size_i]

        _sparse[_index_start: _index_end] = indices_size
        _size_i += 1
        _index_start = _index_end
        _index_end += _sizes[_size_i]

        _sparse[_index_start: _index_end] = csr.indices
        _size_i += 1
        _index_start = _index_end
        _index_end += _sizes[_size_i]

        _sparse[_index_start: _index_end] = indptr_size
        _size_i += 1
        _index_start = _index_end
        _index_end += _sizes[_size_i]

        _sparse[_index_start: _index_end] = csr.indptr

        # _sparse[_index_start: _index_end] = 'Pytracer_sparse_representation'

        return _sparse

    def export_arg(self, *args, **kwargs):

        row = kwargs["row"]
        stats = kwargs["stats"]
        function_id = kwargs["function_id"]
        label = kwargs["label"]
        name = kwargs["name"]
        time = kwargs["time"]
        backtrace = kwargs["backtrace"]
        function_grp = kwargs["hdf5_function_group"]

        if stats is None or stats == [] or stats.shape() == (0,):
            return

        ndim = stats.ndim()

        raw_mean = stats.mean()
        raw_std = stats.std()
        raw_sig = stats.sig()

        if ndim == 0:
            mean = raw_mean
            std = raw_std
            sig = raw_sig
            info = str(stats.values()[0])
        else:
            mean = np.mean(raw_mean, dtype=np.float64)
            std = np.mean(raw_std, dtype=np.float64)
            sig = np.mean(raw_sig, dtype=np.float64)
            info = None

        row["id"] = function_id
        row["label"] = label
        row["name"] = name
        row["time"] = time
        row["mean"] = mean
        row["std"] = std
        row["sig"] = sig
        row["BacktraceDescription/filename"] = backtrace.filename
        row["BacktraceDescription/line"] = backtrace.line
        row["BacktraceDescription/lineno"] = backtrace.lineno
        row["BacktraceDescription/name"] = backtrace.name
        row['dtype'] = stats.dtype()
        if info:
            row['info'] = info
        row.append()

        # We create array to keep the object
        if ndim > 0:
            filters = tables.Filters(complevel=9, complib='zlib')

            unique_id = "/".join([label, name])
            _type = stats.dtype()
            if _type == np.dtype("object"):
                _type = np.dtype("float64")

            try:
                atom_type = tables.Atom.from_dtype(_type)
            except Exception:
                return
            shape = stats.shape()
            path = tables.path.join_path(function_grp._v_pathname, unique_id)

            path_ = self._get_path(path)

            group = self.h5file.create_group(path_,
                                             str(time), createparents=True)

            mean_array = self.h5file.create_carray(
                group, "mean",
                atom=atom_type, shape=shape, filters=filters)
            if spr.issparse(raw_mean):
                start = perf_counter()
                mean_array[:] = self._get_sparse_representation(raw_mean)
                end = perf_counter()
                print(f'mean {end-start}')
            else:
                mean_array[:] = raw_mean

            std_array = self.h5file.create_carray(
                group, "std",
                atom=atom_type, shape=shape, filters=filters)
            if spr.issparse(raw_std):
                start = perf_counter()
                std_array[:] = self._get_sparse_representation(raw_std)
                end = perf_counter()
                print(f'std {end-start}')
            else:
                std_array[:] = raw_std

            sig_array = self.h5file.create_carray(
                group, "sig",
                atom=atom_type, shape=shape, filters=filters)
            if spr.issparse(raw_sig):
                start = perf_counter()
                sig_array[:] = self._get_sparse_representation(raw_sig)
                end = perf_counter()
                print(f'sig {end-start}')
            else:
                sig_array[:] = raw_sig

    def export(self, obj, expectedrows):
        module = obj["module"]  # .replace(".", "$")
        function = obj["function"]  # .replace(".", "$")
        label = obj["label"]
        args = obj["args"]
        backtrace = obj["backtrace"]
        function_id = obj["id"]
        time = obj["time"]
        module_grp_name = f"/{module}"

        assert(module)
        assert(function)

        try:
            tables.path.check_attribute_name(function)
        except ValueError:
            function = 'safename_{function}'

        if module_grp_name in self.h5file:
            module_grp = self.h5file.get_node(module_grp_name)
        else:
            module_grp = self.h5file.create_group("/", module)

        if function in module_grp:
            function_grp = module_grp[function]
            table = function_grp["values"]
        else:
            function_grp = self.h5file.create_group(module_grp, function)
            table = self.h5file.create_table(
                function_grp, "values", description=ExportDescription, expectedrows=expectedrows[0])
        expectedrows[0] = table.nrows + 1000
        row = table.row
        for name, stats in args.items():

            if isinstance(stats, list):
                for i, stat in enumerate(stats):
                    self.export_arg(row=row,
                                    stats=stat,
                                    function_id=function_id,
                                    label=label,
                                    name=f"{name}_TID{i}",
                                    time=time,
                                    backtrace=backtrace,
                                    hdf5_function_group=function_grp)

            if isinstance(stats, dict):
                for name_attr, stat in stats.items():
                    self.export_arg(row=row,
                                    stats=stat,
                                    function_id=function_id,
                                    label=label,
                                    name=f"{name}_{name_attr}",
                                    time=time,
                                    backtrace=backtrace,
                                    hdf5_function_group=function_grp)

            else:
                self.export_arg(row=row,
                                stats=stats,
                                function_id=function_id,
                                label=label,
                                name=name,
                                time=time,
                                backtrace=backtrace,
                                hdf5_function_group=function_grp)

            table.flush()
        self.h5file.flush()
