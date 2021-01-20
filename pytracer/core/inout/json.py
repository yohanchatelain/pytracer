import datetime
import json
from multiprocessing import get_logger
import os

import pytracer.core.utils as ptutils
from pytracer.core.utils.log import get_logger
from pytracer.core.utils.singleton import Singleton
from pytracer.core.config import constant
from pytracer.core.inout import IOInitializer

logger = get_logger()


def split_filename(filename):
    _, name = os.path.split(filename)
    head, count, ext = name.split(os.extsep)
    return (head, count, ext)


def handle_not_json_serializable(self, args):
    if isinstance(args, (tuple, list)):
        list_args = [str(elt) for elt in args]
        return type(args)(list_args)
    if isinstance(args, dict):
        dict_args = dict()
        for k, v in args.items():
            dict_args[k] = self.handle_not_json_serializable(v)
        return dict_args
    return str(args)


class Reader(metaclass=Singleton):

    def __init__(self):
        self.parameters = IOInitializer()

    def read(self, filename):
        try:
            ptutils.check_extension(filename, constant.json_ext)
            fi = open(filename)
            data = json.load(fi)
            return data
        except OSError as e:
            logger.error(f"Can't open JSON file: {filename}", e)
        except json.JSONDecodeError as e:
            logger.error(f"While reading JSON file: {filename}", e)
        except Exception as e:
            logger.critical("Unexpected error", e)


class Writer(metaclass=Singleton):

    count_ofile = 0
    buffer_max = 1024

    def __init__(self):
        self.parameters = IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()
        self.buffer = []

    def _init_ostream(self):
        if self.parameters.filename:
            self.filename = self.get_filename_path(self.parameters.filename)
        else:
            now = datetime.datetime.now().strftime(self.datefmt)
            filename = f"{now}{constant.json_ext}"
            self.filename = self.get_filename_path(filename)
        try:
            if hasattr("ostream", self):
                self.ostream.close()
            self.ostream = open(self.filename, "w")
            self.count_ofile += 1
        except OSError as e:
            logger.error(f"Can't open JSON file: {self.filename}", e)
        except Exception as e:
            logger.critical("Unexpected error", e)

    def get_filename_path(self, filename):
        ptutils.check_extension(filename, constant.json_ext)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.json_ext
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{filename}{os.extsep}"
                f"{self.count_ofile}{ext}")

    def write(self, function, label, args):
        to_write = {"function": function, label: args}
        self.buffer.append(to_write)
        if len(self.buffer) >= self.buffer_max_size:
            try:
                json.dump(self.buffer, self.ostream)
            except TypeError:
                to_write = self.handle_not_json_serializable(to_write)
                json.dump(self.buffer, self.ostream)
            except json.JSONDecodeError as e:
                logger.error(f"While writing in JSON file: {self.filename}", e)
            except Exception as e:
                logger.critical("Unexpected error", e)
            self._init_ostream()

    def inputs(self, function, args):
        self._write(function, "inputs", args)

    def outputs(self, function, args):
        self._write(function.__name__, "outputs", args)

    def backtrace(self, function):
        pass
