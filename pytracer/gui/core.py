import pytracer.callgraph as pc
import tables
import os
import re
import time


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

    __cache = {}
    __labels = {"inputs", "outputs"}
    __modes = ("mean", "std", "sig", 'info')

    def __init__(self, filename, directory):
        if os.path.isfile(filename):
            self.data = tables.File(filename)
        else:
            raise FileNotFoundError

        self.source_path = self.get_source_directory(directory)

    def get_source_directory(self, directory):
        path = f"{directory}{os.sep}sources"
        if os.path.isdir(path):
            return path
        else:
            raise FileNotFoundError(f"Unknown directory path {path}")

    def get_header(self):
        if self.data is None:
            return []

        if hasattr(self, "cached_header"):
            return self.cached_header

        self.cached_header = []
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

    def has_extra_value(self, module, function, label, arg):
        functionnode = self.get_function(module, function)
        if labelnode := getattr(functionnode, label, None):
            if any(map(lambda a: arg in a, [arg._v_name for arg in labelnode])):
                return True
        return False

    def get_extra_value(self, module, function, label=".*", arg=".*", time=".*", mode=".*"):
        if not self.has_extra_value(module, function, label, arg):
            raise KeyError(
                f"group /{module}/{function} does not have extra values")

        self.check_is_valid_label(label)
        self.check_is_valid_mode(mode)

        searchnodename = re.compile(f"{label}_{arg}_{time}_{mode}")
        if (key := (module, function, searchnodename)) in Data.__cache:
            return Data.__cache[key]

        functionnode = self.get_function(module, function)

        labelnode = getattr(functionnode, label)

        for argnode in labelnode:
            if arg in (argnode_name := argnode._v_name):
                argnode = getattr(labelnode, argnode_name)
                if hasattr(argnode, str(time)):
                    timenode = getattr(argnode, str(time))
                    extra_value = getattr(timenode, mode)
                    break

        key = (module, function, searchnodename)
        try:
            Data.__cache[key] = extra_value
        except UnboundLocalError:
            print(f'Inexisting {key}')
            return

        return extra_value

    def filter(self, module, function, filters, col, *argv):
        if self.data is None:
            return None

        if (key := (module, function, col, filters)) in Data.__cache:
            return Data.__cache[key]

        functionnode = self.get_function(module, function)
        values = functionnode.values
        ret = filters(values, col, *argv)

        key = (module, function, col, filters)
        Data.__cache[key] = ret

        return ret

    # def get_first_call_from_line(self, filename, line):
    #     for group in self.data.walk_groups():
    #         for bt in g.values.col('BacktraceDescription'):
    #             sourcefile =


data = None


def init_data(args):
    global data
    data = Data(args.filename, args.directory)


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


def filter_data(data, _filter):
    return [_data for _data in data if _filter(_data)]


def get_ylabel(mode):
    return ylabel[mode]


def is_scalar(value):
    _is_scalar = False
    if hasattr(value, "ndim"):
        _is_scalar = value.ndim == 0
    return _is_scalar


def get_gantt(callgraph):
    pc.core.raw_graphs = pc.core.load(callgraph)
    gantt = []
    extend = gantt.extend
    for _, g in pc.core.raw_graphs.items():
        extend(pc.core.get_gantt(g))
    return gantt


bt_to_id = {}
