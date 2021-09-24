import atexit
import os
import warnings
from collections import namedtuple

import numpy as np
import pytracer.utils as ptutils
import tables
from pytracer.core.config import constant
from pytracer.utils.log import get_logger

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
        if filename := self.parameters.export.filename:
            self.filename = ptutils.get_filename(
                filename, ext=constant.extension.hdf5)
            self.filename_path = self._get_filename_path(self.filename)
        else:
            self.filename = ptutils.get_filename(
                constant.export.filename, ext=constant.extension.hdf5)
            self.filename_path = self._get_filename_path(
                constant.export.filename)

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
        else:
            mean = np.mean(raw_mean, dtype=np.float64)
            std = np.mean(raw_std, dtype=np.float64)
            sig = np.mean(raw_sig, dtype=np.float64)

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
            mean_array[:] = raw_mean

            std_array = self.h5file.create_carray(
                group, "std",
                atom=atom_type, shape=shape, filters=filters)
            std_array[:] = raw_std

            sig_array = self.h5file.create_carray(
                group, "sig",
                atom=atom_type, shape=shape, filters=filters)
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
