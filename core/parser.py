import argparse
import cProfile
import os
import pstats
import time
from pstats import SortKey

from tqdm import tqdm

import pytracer.core.inout as ptinout
from pytracer.core.stats.stats import print_stats
from pytracer.core.config import constant
from pytracer.core.utils.log import get_logger
import pytracer.core.parser_init as parser_init

import pytracer.core.inout.reader as ioreader
import pytracer.core.inout.exporter as ioexporter

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
        for file in tqdm(os.listdir(self.directory), desc="Reading..."):
            abs_file = os.path.abspath(f"{self.directory}{os.sep}{file}")
            if os.path.isfile(abs_file):
                filenames.append(abs_file)
            sizes.add(os.stat(abs_file).st_size)

        if len(sizes) != 1:
            msg = (f"Traces do not have the same size{os.linesep}"
                   f"You are trying to merge data from different "
                   f"program executions or your program is non deterministic ")
            logger.error(msg, caller=self)

        logger.debug(f"List of files to parse: {filenames}")

        iotype = self.auto_detect_format(filenames[0])
        logger.info(f"Auto-detection type: {iotype.name} file")
        filenames_grouped = self.group_files(iotype, filenames)

        stats_values = list()
        for value in zip(*filenames_grouped.values()):
            stat_value = self.merge(value)
            stats_values.append(stat_value)
        return stats_values


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


def main(args):

    parser = Parser(args)

    stats_values = parser.parse_directory()

    time_dict = dict()
    info_dict = dict()
    counter = 0
    pr = None
    toc = None
    tic = None

    if args.timer:
        pr = cProfile.Profile()
        pr.enable()

    for stats_value in tqdm(stats_values,
                            desc="Parsing...",
                            mininterval=0.1,
                            maxinterval=1):
        if args.timer:
            tic = time.perf_counter()

        parse_stat_value(stats_value, info_dict, counter)

        if args.timer:
            toc = time.perf_counter()
            logger.debug(f"[{counter}] parsing time: {toc-tic} seconds")
            time_dict[counter] = (toc-tic)
        counter += 1

    if args.timer:
        pr.disable()
        stats_time = pstats.Stats(pr)
        stats_time.sort_stats(SortKey.CUMULATIVE)
        stats_time.print_stats(10)

    if args.timer:
        pr.enable()

    export = ioexporter.Exporter()
    for stats_value in tqdm(stats_values,
                            desc="Exporting...",
                            mininterval=0.1,
                            maxinterval=1):
        export.export(stats_value)

    if args.timer:
        pr.disable()
        stats_time = pstats.Stats(pr)
        stats_time.sort_stats(SortKey.CUMULATIVE)
        stats_time.print_stats(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pytracer parser")
    parser_init.init_module(parser, dict())
    args = parser.parse_args()
    main(args)
