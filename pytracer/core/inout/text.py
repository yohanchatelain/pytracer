import os
import sys
import traceback

import pytracer.core.inout as ptinout
from pytracer.core.utils.log import get_logger
from pytracer.core.utils.singleton import Singleton
from pytracer.core.config import constant, config as cfg


logger = get_logger()


def split_filename(filename):
    _, name = os.path.split(filename)
    head, count, ext = name.split(os.extsep)
    return (head, count, ext)


class Writer(metaclass=Singleton):

    wrapper = ptinout.wrapper
    wrapper_class = ptinout.wrapper_class
    wrapper_instance = ptinout.wrapper_instance
    ostream_default = sys.stdout

    def __init__(self):
        self.parameters = ptinout.IOInitializer()
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

    def write(self, message, module, function, args):
        self.ostream.write(f"{message},{module},{function},{args}{os.linesep}")

    def inputs(self, function, args):
        if hasattr(function, "__module__"):
            module = getattr(function, "__module__")
        else:
            clss = getattr(function, "__class__")
            module = getattr(clss, "__module__")
        function_name = getattr(function, "__name__", function)
        self.write("inputs", module, function_name, args)

    def inputs_instance(self, instance, args):
        if hasattr(instance.obj, "__module__"):
            module = getattr(instance.obj, "__module__")
        else:
            clss = getattr(instance.obj, "__class__")
            module = getattr(clss, "__module__")
        function_name = getattr(instance, "__name__")
        self.write("inputs", module, function_name, args)

    def outputs(self, function, args):
        if hasattr(function, "__module__"):
            module = getattr(function, "__module__")
        else:
            clss = getattr(function, "__class__")
            module = getattr(clss, "__module__")
        function_name = getattr(function, "__name__", function)
        self.write("outputs", module, function_name, args)

    def outputs_instance(self, instance, args):
        if hasattr(instance.obj, "__module__"):
            module = getattr(instance.obj, "__module__")
        else:
            clss = getattr(instance.obj, "__class__")
            module = getattr(clss, "__module__")
        function_name = getattr(instance, "__name__")
        self.write("outputs", module, function_name, args)

    def backtrace(self):
        if cfg.io.backtrace:
            stack = traceback.extract_stack()
            return stack
        return None


class Reader(metaclass=Singleton):

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
