import numpy as np
import tables
import os
import re


ylabel = {"mean": "Mean", "sig": "Significant bits",
          "std": "Standard deviation"}


class DataError(Exception):
    pass


class ModeError(DataError):

    def __init__(self, mode, message):
        self.mode = mode
        self.message = message


class LabelError(DataError):

    def __init__(self, label, message):
        self.label = label
        self.message = message


class ModuleNotFound(DataError):

    def __init__(self, module, message):
        self.module = module
        self.message = message


class FunctionNotFound(DataError):

    def __init__(self, function, message):
        self.function = function
        self.message = message


class NodeNotFound(DataError):

    def __init__(self, node, message):
        self.node = node
        self.message = message


class Data:

    __labels = {"inputs", "outputs"}
    __modes = ("mean", "std", "sig")

    def __init__(self, filename=None):
        if filename is None:
            self.data = None
        elif os.path.isfile(filename):
            self.data = tables.File(filename)
        else:
            raise FileNotFoundError

    def get_header(self):
        if self.data is None:
            return []

        if hasattr(self, "cached_header"):
            return self.cached_header

        self.cached_header = list()
        modules = self.data.iter_nodes("/")
        for module in modules:
            for function in module:
                self.cached_header.append(
                    {"module": module._v_name,
                        "function": function._v_name}
                )
        return self.cached_header

    def get_module(self, module):
        if f"/{module}" not in self.data:
            raise ModuleNotFound(module, "module not found")
        return getattr(self.data.root, module)

    def get_function(self, module, function):
        modulenode = None
        if isinstance(module, tables.Group):
            modulenode = module
        elif isinstance(module, str):
            modulenode = self.get_module(module)
        else:
            raise TypeError("Unknown module type {type(module)}")

        if function not in modulenode:
            raise FunctionNotFound(
                function, f"function {function} not found in module {module}")

        return getattr(modulenode, function)

    def is_valid_label(self, label):
        return label in Data.__labels

    def check_is_valid_label(self, label):
        if not self.is_valid_label(label):
            raise LabelError(label, f"allowed labels are {Data.__labels}")

    def is_valid_mode(self, mode):
        return mode in Data.__modes

    def check_is_valid_mode(self, mode):
        if not self.is_valid_mode(mode):
            raise ModeError(mode, f"allowed modes are {Data.__modes}")

    def is_value(self, node):
        return isinstance(node, tables.table.Table)

    def is_extra_value(self, node):
        return isinstance(node, tables.carray.CArray)

    def has_extra_value(self, module, function):
        functionnode = self.get_function(module, function)
        for node in functionnode:
            if self.is_extra_value(node):
                return True
        return False

    def get_extra_value(self, module, function, label=".*", arg=".*", time=".*", mode=".*"):
        if not self.has_extra_value(module, function):
            raise KeyError(
                f"group /{module}/{function} does not have extra values")

        self.check_is_valid_label(label)
        self.check_is_valid_mode(mode)

        searchnodename = re.compile(f"{label}_{arg}_{time}_{mode}")
        functionnode = self.get_function(module, function)
        foundnodes = []
        for node in functionnode:
            if searchnodename.fullmatch(node.name):
                foundnodes.append(node)

        return foundnodes

    def filter(self, module, function, filters, col):
        if self.data is None:
            return None

        functionnode = self.get_function(module, function)
        values = functionnode.values
        ret = [x[col] for x in values.iterrows() if filters(x)]
        return ret


data = Data()


def init_data(args):
    global data
    filename = "test.h5"
    data = Data(filename)


def get_data():
    return data


def getitem(_dict, _item):
    item = None
    if _item in _dict:
        item = _dict[_item]
    return item


def get_active_row(selected_rows, data):
    return [data[selected_row]
            for selected_row in selected_rows]


def get_sig(value):
    sig = value
    if hasattr(value, "ndim"):
        if value.ndim > 0:
            sig = np.mean(value)
    return sig


def filter_data(data, _filter):
    return [_data for _data in data if _filter(_data)]


def get_ylabel(mode):
    return ylabel[mode]


def is_scalar(value):
    _is_scalar = False
    if hasattr(value, "ndim"):
        _is_scalar = value.ndim == 0
    return _is_scalar


# Data
# header_path = ".__pytracercache__/stats/header.0.pkl"
# stats_path = ".__pytracercache__/stats/stats.0.pkl"

bt_to_id = dict()
# stats_data = read_stats(stats_path)
# header_data = read_header(header_path)
# header_table = get_table(header_data)

__max_sig = {
    np.dtype("int8"): 8,
    np.dtype("int16"): 16,
    np.dtype("int32"): 32,
    np.dtype("int64"): 64,
    np.dtype("float16"): 11,
    np.dtype("float32"): 24,
    np.dtype("float64"): 53,
    np.dtype("float128"): 112
}
