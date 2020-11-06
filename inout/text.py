import os
import sys

import utils.log
import utils.singleton
from config import constant

import inout

logger = utils.log.get_log()


def split_filename(filename):
    _, name = os.path.split(filename)
    head, count, ext = name.split(os.extsep)
    return (head, count, ext)


class Writer(metaclass=utils.singleton.Singleton):

    wrapper = inout.wrapper
    ostream_default = sys.stdout

    def __init__(self):
        self.parameters = inout.IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()

    def _init_ostream(self):
        if self.parameters.filename:
            utils.utils.check_extension(
                self.parameters.filename, constant.text_ext)
            self.ostream = open(self.parameters.filename, "w")
        else:
            self.ostream = self.ostream_default

    def get_filename(self, filename):
        utils.check_extension(filename, constant.text_ext)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.text_ext
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{filename}{os.extsep}"
                f"{self.count_ofile}{ext}")

    def write(self, message, function, args):
        self.ostream.write(f"{message},{function},{args}{os.sepline}")

    def inputs(self, function, args):
        self._write("inputs", function.__name__, args)

    def outputs(self, function, args):
        self._write("outputs", function.__name__, args)

    def backtrace(self, function):
        pass


class Reader(metaclass=utils.singleton.Singleton):

    def __init__(self):
        self.parameters = inout.IOInitializer()

    def read(self, filename):
        try:
            utils.utils.check_extension(filename, constant.text_ext)
            fi = open(filename)
            data = []
            for line in fi:
                if line.startswith("#") or line == "":
                    continue
                label, function, args = line.strip().split(",")
                d = {"label": label, "function": function, "args": args}
                self.data.append(d)
            return data
        except OSError as e:
            logger.error(f"Can't open Text file: {filename}", e)
        except Exception as e:
            logger.error(f"While reading Text file: {filename}", e)
