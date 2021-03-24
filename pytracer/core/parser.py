import argparse
import copy
import os
import pickle
import tempfile
from enum import Enum, auto

import networkx as nx
import pytracer.core.inout as ptinout
import pytracer.core.inout.exporter as ioexporter
import pytracer.core.inout.reader as ioreader
import pytracer.core.parser_init as parser_init
import pytracer.utils.context as ptcontext
from pytracer.core.config import constant
from pytracer.core.stats.stats import print_stats
from pytracer.utils.log import get_logger
from tqdm import tqdm

logger = get_logger()


class Group:

    def __init__(self, iotype, data):
        self.iotype = iotype
        self.reader = ioreader.Reader()
        self.parse_filenames(data)
        self.init_reader()

    def __repr__(self):
        return str(self._data)

    # Data: List of filename
    def parse_filenames(self, data):
        self._filenames = dict()
        for filename in data:
            _, count, _ = ptinout.split_filename(filename)
            self._filenames[int(count)] = filename

    def init_reader(self):
        self._index_file = min(self._filenames)
        self._nb_file = len(self._filenames)
        filename = self._filenames[self._index_file]
        self._data = self.reader.read(filename)
        self._index_data = 0
        self._nb_data = len(self._data)

    def __iter__(self):
        return self

    def __next__(self):
        if self._index_data >= self._nb_data:
            # We have finish to read this index
            # Look if there is a another file
            self._index_file += 1
            if self._index_file >= self._nb_file:
                raise StopIteration
            filename = self._filenames[self._index_file]
            self._data = self.reader.read(filename)
            self._index_data = 0
            self._nb_data = len(self._data)

        data = self._data[self._index_data]
        self._index_data += 1
        return data


class Parser:

    def __init__(self, args):
        self.init_args(args)
        self.check_args(args)

    def init_args(self, args):
        self.online = args.online
        self.batch_size = args.batch_size
        self.directory = None
        self.filename = None

    def check_args(self, args):
        if args.directory:
            if not os.path.isdir(args.directory):
                logger.error(f"{args.directory} is not a directory")
            self.directory = args.directory
        if args.filename:
            if not os.path.isfile(args.filename):
                logger.error(f"{args.filename} is not a file")
            self.filename = args.filename

    def auto_detect_format(self, filename):
        if filename.endswith(constant.text_ext):
            return ptinout.IOType.TEXT
        if filename.endswith(constant.json_ext):
            return ptinout.IOType.JSON
        if filename.endswith(constant.pickle_ext):
            return ptinout.IOType.PICKLE
        return None

    # Regroup files that belongs to the same trace
    # ie, sharing the same date
    # <date>.<count>.<filename>.<ext>
    def group_files(self, iotype, filenames):
        groups = dict()
        while len(filenames) > 0:
            filename = filenames[0]
            name, _, _ = ptinout.split_filename(filename)
            similar = [f for f in filenames if name in f]
            groups[name] = Group(iotype, similar)
            for visited in similar:
                filenames.pop(filenames.index(visited))
        return groups

    def merge_dict(self, args):
        from pytracer.core.stats.stats import get_stats
        args_name = [arg.keys() for arg in args]
        for arg_name in args_name:
            assert(all(map(lambda d: d == arg_name, args_name)))

        stats_dict = dict()
        for arg_name in args_name[0]:
            arg_value = [arg[arg_name] for arg in args]
            arg_stat = get_stats(arg_value)
            stats_dict[arg_name] = arg_stat

        return stats_dict

    # def merge_raw(self, raws):
    #     return stats.get_stats(raws)

    def _merge(self, values, attr, do_not_check=False):
        attrs = None
        if isinstance(attr, str):
            attrs = [value[attr] for value in values]
        elif callable(attr):
            attrs = [attr(value) for value in values]
        else:
            logger.error(f"Unknow type attribute during merge: {attr}")

        if not do_not_check and len(set(attrs)) != 1:
            logger.error(
                f"Samples can't be merged: different {attr} found {attrs}")
        return attrs

    def merge(self, values):

        # Ensure that all attributes are the same
        # Except for function id since it changes from an execution to another
        function_id = self._merge(values, "id", do_not_check=True)
        times = self._merge(values, "time")
        modules = self._merge(values, "module")
        functions = self._merge(values, "function")
        labels = self._merge(values, "label")
        backtraces = self._merge(values, "backtrace", do_not_check=True)

        # Args may be different
        args = self._merge(values, "args", do_not_check=True)

        stats_args = self.merge_dict(args)

        # We can pick any of the list since
        # we ensure that they are equal
        function_id = function_id.pop()
        time = times.pop()
        module = modules.pop()
        function = functions.pop()
        label = labels.pop()
        backtrace = backtraces.pop()

        return {"id": function_id,
                "time": time,
                "module": module,
                "function": function,
                "label": label,
                "backtrace": backtrace,
                "args": stats_args}

    def parse_directory(self):

        filenames = list()
        sizes = set()
        for file in os.listdir(self.directory):
            abs_file = os.path.abspath(f"{self.directory}{os.sep}{file}")
            if os.path.isfile(abs_file):
                filenames.append(abs_file)
            sizes.add(os.stat(abs_file).st_size)

        if len(sizes) != 1:
            msg = (f"Traces do not have the same size{os.linesep}"
                   f"You are trying to merge data from different "
                   f"program executions or your program is non deterministic {os.linesep}"
                   f"sizes: {sizes}")
            logger.error(msg, caller=self)
        else:
            print(f"Filesize: {sizes}")
        logger.debug(f"List of files to parse: {filenames}")

        iotype = self.auto_detect_format(filenames[0])
        logger.info(f"Auto-detection type: {iotype.name} file")
        filenames_grouped = self.group_files(iotype, filenames)

        if self.online:
            for value in tqdm(zip(*filenames_grouped.values()), desc="Parsing..."):
                yield self.merge(value)
        else:
            stats_values = list()
            for value in tqdm(zip(*filenames_grouped.values()), desc="Parsing..."):
                stats_values.append(self.merge(value))
                if len(stats_values) % self.batch_size == 0:
                    yield stats_values
                    stats_values.clear()


def parse_stat_value(stats_value, info_dict, counter):
    function_id = stats_value["id"]
    time = stats_value["time"]
    module = stats_value["module"]
    function = stats_value["function"]
    label = stats_value["label"]

    args = stats_value["args"]
    info_dict[counter] = {"id": function_id,
                          "time": time,
                          "module": module,
                          "function": function,
                          "label": label}
    logger.debug("==============================")
    logger.debug((f"[{counter}]",
                  f"id: {function_id}",
                  f"time: {time}",
                  f"module: {module},",
                  f"function: {function},"
                  f"{label}"))
    # if isinstance(args, dict):
    for arg, stat in args.items():
        print_stats(arg, stat)


class EdgeType(Enum):
    CAUSAL = auto()
    HIERARCHICAL = auto()
    DEPENDENCY = auto()
    CYCLE = auto()


class CallChain:

    _input_label = "inputs"
    _output_label = "outputs"

    _id_index = 0
    _name_index = _id_index + 1
    _label_index = _name_index + 1
    _bt_index = _label_index + 1
    _time_index = _bt_index + 1

    _bt_filename_index = 0
    _bt_line_index = _bt_filename_index + 1
    _bt_lineno_index = _bt_line_index + 1
    _bt_name_index = _bt_lineno_index + 1

    def __init__(self):
        fo = open("callgraph.pkl", "wb")
        self._pickler = pickle.Pickler(fo, protocol=pickle.HIGHEST_PROTOCOL)
        self._stack = []

    def to_call(self, obj):
        module = obj["module"]  # .replace(".", "$")
        function = obj["function"]  # .replace(".", "$")
        label = obj["label"]
        backtrace = obj["backtrace"]
        time = obj['time']
        fid = obj["id"]

        name = f"{module}.{function}"
        bt = (backtrace.filename,
              backtrace.line,
              backtrace.lineno,
              backtrace.name)

        return (fid, name, label, bt, time)

    @staticmethod
    def call_to_str(call, sep):
        return sep.join(map(str, call))

    @staticmethod
    def str_to_call(str, sep):
        [fid, name, label, bt, time] = str.split(sep)
        # get original type
        fid_ori = int(fid)
        bt_ori = eval(bt)
        time_ori = int(time)
        return (fid_ori, name, label, bt_ori, time_ori)

    def have_same_origin(self, call1, call2):
        same_id = CallChain.get_id(call1) == CallChain.get_id(call2)
        same_name = CallChain.get_name(call1) == CallChain.get_name(call2)
        same_bt = CallChain.get_bt(call1) == CallChain.get_bt(call2)
        return all((same_id, same_name, same_bt))

    @classmethod
    def get_id(cls, call):
        return call[cls._id_index]

    @classmethod
    def get_name(cls, call):
        return call[cls._name_index]

    @classmethod
    def get_label(cls, call):
        return call[cls._label_index]

    @classmethod
    def get_bt(cls, call):
        return call[cls._bt_index]

    @classmethod
    def get_lineno(cls, call):
        return call[cls._bt_index][cls._bt_lineno_index]

    @classmethod
    def get_filename(cls, call):
        return call[cls._bt_index][cls._bt_filename_index]

    @classmethod
    def get_line(cls, call):
        return call[cls._bt_index][cls._bt_line_index]

    @classmethod
    def get_caller(cls, call):
        return call[cls._bt_index][cls._bt_name_index]

    @classmethod
    def get_time(cls, call):
        return call[cls._time_index]

    def is_input_call(self, call):
        return call[self._label_index] == self._input_label

    def print_stack(self, stack, name=None, to_print=False):
        if not to_print:
            return
        stack.reverse()
        print('[')
        if name:
            for elt in stack:
                print(f"  -{name(elt)}")
        else:
            for elt in stack:
                print(f"  -{elt}")
        print(']')
        stack.reverse()

    def to_tree(self, short=False):
        # print("--- Start building tree ---")
        G = nx.DiGraph()
        last_input_call = None
        parents = []
        children = []
        children_stack = []

        stack_nb = self.to_number(as_dict=True)
        if short:
            def pp(call):
                if isinstance(call, list):
                    return list(map(lambda c: stack_nb[c], call))
                else:
                    return stack_nb[call]
        else:
            def pp(call): return call

        last_node = None
        last_node_cycle = 1

        to_print = len(self._stack) < 4
        printd = print if to_print else lambda x: None

        if len(self._stack) == 2:
            G.add_node(self._stack[0])
            return G

        i = ''
        for j, call in enumerate(self._stack, start=1):
            printd(f"{i} (*) {j} Visit call {pp(call)}")
            printd(f"{i+'|'}Current children stack: ")
            self.print_stack(children_stack, pp, to_print=to_print)
            if self.is_input_call(call):

                if last_input_call is not None:
                    if not self.have_same_origin(last_input_call, call):
                        G.add_edge(last_input_call, call,
                                   edgetype=EdgeType.CAUSAL)

                last_input_call = call

                if children_stack:
                    children = children_stack.pop()
                else:
                    children = []

                printd("children.append(call)")
                children.append(call)
                self.print_stack(children_stack, pp, to_print=to_print)

                printd("children_stack.append(children)")
                children_stack.append(children)
                self.print_stack(children_stack, pp, to_print=to_print)

                printd("children = []")
                children = []
                printd(f"{i+'|'}Push new children -> ")
                self.print_stack(children_stack, pp, to_print=to_print)
            else:  # ouput-call
                children = children_stack.pop()
                printd(f"{i+'|'}Pop children {pp(children)} -> ")
                self.print_stack(children_stack, pp, to_print=to_print)

            if parents:
                parent = parents.pop()
                printd(f"{i+'|'}Parent {pp(parent)}")
                if self.isclosure(parent, call):
                    printd(f"{i+'|'}Is closure {pp(parent)} {pp(call)}")
                    printd(f"{i+'|'}Create node {pp(parent)}")

                    if last_node:
                        if self.have_same_origin(last_node, parent):
                            last_node_cycle += 1
                        else:
                            printd(f"{i+'|'} add node {pp(parent)}")
                            printd(f"{i+'|'} add node {pp(last_node)}")
                            G.add_node(parent)
                            G.add_node(last_node)
                            if last_node_cycle > 1:
                                printd(
                                    f"{i+'|'} add edge {pp(last_node)} -> {pp(last_node)}")
                                G.add_edge(last_node, last_node,
                                           cycle=last_node_cycle,
                                           edgetype=EdgeType.CAUSAL)
                                last_node_cycle = 1
                            last_node = parent
                    else:
                        last_node = parent

                    if children:
                        printd(f"{i+'|'}Has children {pp(children)}")
                        for child in children:
                            printd(
                                f"{i+'|'}Add edge {pp(parent)}->{pp(child)}")
                            G.add_edge(parent, child,
                                       edgetype=EdgeType.HIERARCHICAL)
                    printd(f"{i+'|'} Append child {pp(parent)}")

                    # children.append(parent)
                    i = i[:-1]
                else:
                    i += '|'
                    children_stack.append(children)
                    parents.append(parent)
                    parents.append(call)
            else:
                printd(f"{i+'|'}No parent")
                parents.append(call)
                children_stack.append(children)
                i += '|'
            printd(f"{i+'|'}Current children stack: ")
            self.print_stack(children_stack, pp, to_print=to_print)
        # print("--- End building tree ---")

        return G

    def dump(self, obj):
        self._pickler.dump(obj)

    def isclosure(self, call1, call2):
        (id1, name1, _, bt1, t1) = call1
        (id2, name2, _, bt2, t2) = call2

        if call1 == (id2, name2, self._input_label, bt2, t2) and \
                call2 == (id1, name1, self._output_label, bt1, t1):
            return True
        else:
            return False

    def to_number(self, as_dict=False):

        counter = 1
        call_to_id = dict()
        for call in self._stack:
            key = f"{call[self._id_index]}{call[self._name_index]}{call[self._bt_index]}"
            if key not in call_to_id:
                call_to_id[key] = f"{counter}"
                counter += 1

        _str = "" if not as_dict else dict()
        for call in self._stack:
            key = f"{call[self._id_index]}{call[self._name_index]}{call[self._bt_index]}"
            dir = "<" if call[self._label_index] == self._input_label else ">"
            if as_dict:
                _str[call] = f"{call_to_id[key]}{dir}"
            else:
                _str += f"{call_to_id[key]}{dir} "

        return _str

    def push(self, call, short=False):
        # print(f"{self._indent}Push {call} onto stack -> {self._stack}")

        if self._stack == []:
            self._stack.append(call)
            # print(f"{self._indent}  1st: {self._stack[0]}")
        else:
            self._stack.append(call)

            fst_call = self._stack[0]
            # (fst_id, fst_name, fst_label) = fst_call
            # (prev_id, prev_name, prev_label) = self._stack[len(self._stack)-2]
            # (cur_id, cur_name, cur_label) = call

            # print(f"{self._indent}   1st: {self._stack[0]}")
            # print(f"{self._indent}  Last: {call}")
            if self.isclosure(fst_call, call):

                stack_nb = self.to_number(as_dict=True)
                if short:
                    def pp(call):
                        if isinstance(call, list):
                            return list(map(lambda c: stack_nb[c], call))
                        else:
                            return stack_nb[call]
                else:
                    def pp(call): return call

                G = self.to_tree(short=True)
                # print("Tree")
                # for node in G.nodes():
                #     print(f'node {node}')
                # for e1, e2, d in G.edges(data=True):
                #     print(f'edge [{d["edgetype"]}] {pp(e1)}->{pp(e2)}')
                self.dump(G)
                self._stack.clear()
                # self._indent = ""
            # elif prev_id == cur_id and \
            #         prev_label == self._input_label and \
            #         cur_label == self._output_label and \
            #         prev_name == cur_name:
            #     self._indent = self._indent[:-1]
            # else:
            #     self._indent += " "


def main(args):

    parser = Parser(args)

    stats_values = parser.parse_directory()

    # Construct call chain
    callchain = CallChain()

    export = ioexporter.Exporter()
    if args.online:
        for stats_value in tqdm(stats_values,
                                desc="Exporting...",
                                mininterval=0.1,
                                maxinterval=1):
            call = callchain.to_call(stats_value)
            callchain.push(call, short=True)
            export.export(stats_value)
    else:
        for stats_value_batch in tqdm(stats_values,
                                      desc="Exporting...",
                                      mininterval=0.1,
                                      maxinterval=1):
            for stats_value in stats_value_batch:
                call = callchain.to_call(stats_value)
                callchain.push(call, short=True)
                export.export(stats_value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pytracer parser")
    parser_init.init_module(parser)
    args = parser.parse_args()

    t = tempfile.NamedTemporaryFile()
    t.write(ptcontext.verificarlo.getenv(
        ptcontext.verificarlo.BackendType.IEEE))
    env = {"VFC_BACKENDS_FROM_FILE": t.name}
    env_excluded = ["VFC_BACKENDS"]

    with ptcontext.context.ContextManager(env, env_excluded):
        main(args)

    t.close()
