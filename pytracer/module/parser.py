import argparse
import os
import pickle
import time
from enum import Enum, auto

import networkx as nx
import pytracer.core.inout as ptinout
import pytracer.core.inout._init as _init
import pytracer.core.inout.exporter as ioexporter
import pytracer.core.inout.reader as ioreader
import pytracer.module.parser_init as parser_init
import pytracer.utils as ptutils

from pytracer.core.config import constant
from pytracer.core.stats.stats import print_stats
from pytracer.module.info import register
from pytracer.utils.log import get_logger
from tqdm import tqdm

logger = get_logger()


class Group:

    '''
    Group class holds several traces and
    facilitates iteration over them
    '''

    def __init__(self, iotype, filenames):
        self.iotype = iotype
        self.init_reader(filenames)

    def init_reader(self, filenames):
        self.readers = [iter(ioreader.Reader(f)) for f in filenames]

    def __iter__(self):
        self.iterator = zip(*self.readers)
        return self

    def __next__(self):
        try:
            return next(self.iterator)
        except EOFError:
            raise StopIteration


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
                logger.error(
                    f"{args.directory} is not a directory", caller=self)
            self.directory = args.directory
        if args.filename:
            if not os.path.isfile(args.filename):
                logger.error(f"{args.filename} is not a file", caller=self)
            self.filename = args.filename

    def auto_detect_format(self, filename):
        if filename.endswith(constant.extension.pickle):
            return ptinout.IOType.PICKLE
        return None

    def merge_dict(self, args):
        from pytracer.core.stats.stats import get_stats
        args_name = [arg.keys() for arg in args]
        for arg_name in args_name:
            assert (all([d == arg_name for d in args_name]))

        stats_dict = {}
        for arg_name in args_name[0]:
            arg_value = [arg[arg_name] for arg in args]
            arg_stat = get_stats(arg_value)
            stats_dict[arg_name] = arg_stat

        return stats_dict

    def _merge(self, values, attr, do_not_check=False):
        attrs = None
        try:
            if isinstance(attr, str):
                attrs = [value[attr] for value in values]
            elif callable(attr):
                attrs = [*map(attr, values)]
            else:
                logger.error(f"Unknow type attribute during merging: {attr}")
        except KeyError:
            return [{}]*len(values)
        except Exception as e:
            logger.critical(
                f"Error while merging traces {values} for attribute {attr}", caller=self, error=e)

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

    def get_traces(self):
        filenames = []
        sizes = set()

        def abspath(file):
            return f"{self.directory}{os.sep}{file}"

        filenames = [os.path.abspath(abspath(file))
                     for file in os.listdir(self.directory) if os.path.isfile(abspath(file))]
        sizes = set([os.stat(file).st_size for file in filenames])

        if filenames == []:
            logger.error("No traces to analyze", caller=self)

        if len(sizes) != 1:
            msg = (f"Traces do not have the same size{os.linesep}"
                   f"You are trying to merge data from different "
                   f"program executions or your program is non deterministic {os.linesep}"
                   f"sizes: {sizes}")
            logger.warning(msg, caller=self)

        logger.debug(f"List of files to parse: {filenames}", caller=self)
        logger.debug(f"Filesize: {sizes}", caller=self)

        return filenames

    def parse_traces(self, traces):

        iotype = self.auto_detect_format(traces[0])
        logger.info(f"Auto-detection type: {iotype.name} file", caller=self)
        filenames_grouped = Group(iotype, traces)

        if self.online:
            for value in tqdm(filenames_grouped, desc="Parsing..."):
                yield self.merge(value)
        else:
            stats_values = []
            append = stats_values.append
            for value in tqdm(filenames_grouped, desc="Parsing..."):
                append(self.merge(value))
                if len(stats_values) % self.batch_size == 0:
                    yield stats_values
                    stats_values.clear()
            if len(stats_values) > 0:
                yield stats_values


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
        self.parameters = _init.IOInitializer()
        self._init_filename()
        fo = open("callgraph.pkl", "wb")
        self._pickler = pickle.Pickler(fo, protocol=pickle.HIGHEST_PROTOCOL)
        self._stack = []

    def _init_filename(self):
        filename = self.parameters.callgraph
        self.filename = ptutils.get_filename(
            filename, constant.extension.pickle)
        self.filename_path = self._get_filename_path(self.filename)

    def _get_filename_path(self, filename):
        ptutils.check_extension(filename, constant.extension.pickle)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.extension.pickle
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{self.parameters.cache_stats}{os.sep}"
                f"{filename}{ext}")

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
                    return [stack_nb[c] for c in call]
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

        if call1 == (id2, name2, self._input_label, bt2, t2) and call2 == (id1, name1, self._output_label, bt1, t1):
            is_closure = True
        else:
            is_closure = False

        return is_closure

    def to_number(self, as_dict=False):

        counter = 1
        call_to_id = {}
        for call in self._stack:
            key = f"{call[self._id_index]}{call[self._name_index]}{call[self._bt_index]}"
            if key not in call_to_id:
                call_to_id[key] = f"{counter}"
                counter += 1

        _str = "" if not as_dict else {}
        for call in self._stack:
            key = f"{call[self._id_index]}{call[self._name_index]}{call[self._bt_index]}"
            dir = "<" if call[self._label_index] == self._input_label else ">"
            if as_dict:
                _str[call] = f"{call_to_id[key]}{dir}"
            else:
                _str += f"{call_to_id[key]}{dir} "

        return _str

    def push(self, call, short=False):

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
                            return [stack_nb[c] for c in call]
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
    enable_timer = False

    if enable_timer:
        print("STARTING")
        start = time.time()

    parser = Parser(args)

    traces = parser.get_traces()
    register.add_traces(traces)
    stats_values = parser.parse_traces(traces)

    # Construct call chain
    callchain = CallChain()

    export = ioexporter.Exporter()
    register.set_aggregation(export.get_filename(), export.get_filename_path())

    expectedrows = [10]

    if args.online:
        for stats_value in tqdm(stats_values,
                                desc="Exporting...",
                                mininterval=0.1,
                                maxinterval=1):
            call = callchain.to_call(stats_value)
            callchain.push(call, short=True)
            export.export(stats_value, expectedrows)
    else:
        for stats_value_batch in tqdm(stats_values,
                                      desc="Exporting...",
                                      mininterval=0.1,
                                      maxinterval=1):
            for stats_value in stats_value_batch:
                call = callchain.to_call(stats_value)
                callchain.push(call, short=True)
                export.export(stats_value, expectedrows)

    if enable_timer:
        end = time.time()
        print(f"DONE in time: {end - start}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pytracer parser")
    subparser = parser.add_subparsers(title="pytracer modules",
                                      help="pytracer modules",
                                      dest="pytracer_module")

    parser_init.init_module(subparser)
    args = parser.parse_args()
    main(args)
