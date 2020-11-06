import argparse
import os

import inout
import utils.log
from config import constant
import stats

logger = utils.log.get_log()


class Group:

    def __init__(self, iotype, data):
        self.iotype = iotype
        self.reader = inout.reader(self.iotype)
        self.parse_filenames(data)
        self.init_reader()

    def __repr__(self):
        return str(self._data)

    # Data: List of filename
    def parse_filenames(self, data):
        self._filenames = dict()
        for filename in data:
            _, count, _ = inout.split_filename(filename)
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
            return inout.IOType.TEXT
        if filename.endswith(constant.json_ext):
            return inout.IOType.JSON
        if filename.endswith(constant.pickle_ext):
            return inout.IOType.PICKLE
        return None

    # Regroup files that belongs to the same trace
    # ie, sharing the same date
    # <date>.<count>.<filename>.<ext>
    def group_files(self, iotype, filenames):
        groups = dict()
        while len(filenames) > 0:
            filename = filenames[0]
            name, _, _ = inout.split_filename(filename)
            similar = [f for f in filenames if name in f]
            groups[name] = Group(iotype, similar)
            for visited in similar:
                filenames.pop(filenames.index(visited))
        return groups

    def merge_dict(self, args):
        args_name = [arg.keys() for arg in args]
        for arg_name in args_name:
            assert(all(map(lambda d: d == arg_name, args_name)))

        stats_dict = dict()
        for arg_name in args_name[0]:
            arg_value = [arg[arg_name] for arg in args]
            logger.debug(f"arg_value: {arg_value}")
            arg_stat = stats.Statistic(arg_value)
            stats_dict[arg_name] = arg_stat

        return stats_dict

    def merge_raw(self, raws):
        logger.debug(f"arg_value: {raws}")
        return stats.Statistic(raws)

    def merge(self, values):
        # Ensure that all functions are the same
        functions = [value["function"] for value in values]
        assert(len(set(functions)) == 1)

        # Ensure that all label are the same
        labels = [value["label"] for value in values]
        assert(len(set(labels)) == 1)

        # Ensure all argument have the same type
        args = [value["args"] for value in values]
        args_types = [type(arg) for arg in args]
        assert(len(set(args_types)) == 1)

        arg_type = args_types[0]
        if arg_type == dict:
            stats_args = self.merge_dict(args)
        else:
            stats_args = self.merge_raw(args)

        # We can pick any of the list since
        # we ensure that they are equal
        function = functions[0]
        label = labels[0]

        return {"function": function, "label": label, "args": stats_args}

    def parse_directory(self):

        filenames = list()
        for file in os.listdir(self.directory):
            abs_file = os.path.abspath(f"{self.directory}{os.sep}{file}")
            if os.path.isfile(abs_file):
                filenames.append(abs_file)

        logger.debug(f"List of files to parse: {filenames}")

        iotype = self.auto_detect_format(filenames[0])
        logger.info(f"Auto-detection type: {iotype.name} file")
        filenames_grouped = self.group_files(iotype, filenames)

        stats_values = list()
        for value in zip(*filenames_grouped.values()):
            stat_value = self.merge(value)
            stats_values.append(stat_value)
        return stats_values


if __name__ == "__main__":
    parser_args = argparse.ArgumentParser(description="Pytracer parser")
    mutual_exclusion = parser_args.add_mutually_exclusive_group()
    mutual_exclusion.add_argument("--filename", help="only parse <filename>")
    mutual_exclusion.add_argument("--directory", default=constant.cache,
                                  help=("parse all files in <directory>"
                                        "and merge them"))
    parser_args.add_argument("--format", choices=constant.iotypes,
                             help="format of traces (auto-detected by default)")
    args = parser_args.parse_args()

    parser = Parser(args)
    stats_values = parser.parse_directory()
    for stats_value in stats_values:
        function = stats_value["function"]
        label = stats_value["label"]
        args = stats_value["args"]
        logger.debug(f"function: {function}, {label}")

        if isinstance(args, stats.Statistic):
            logger.debug(f"\tmean: {args.mean()}")
            logger.debug(f"\t std: {args.std()}")
            logger.debug(f"\t sig: {args.significant_digits()}")
        else:
            for k, v in args.items():
                logger.debug(f"\tArgs {k}")
                logger.debug(f"\t\tmean: {v.mean()}")
                logger.debug(f"\t\t std: {v.std()}")
                logger.debug(f"\t\t sig: {v.significant_digits()}")
