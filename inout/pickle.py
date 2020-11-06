import datetime
import os
import pickle

import utils.log
from config import constant
from utils.singleton import Singleton

import inout

logger = utils.log.get_log()


def split_filename(filename):
    _, name = os.path.split(filename)
    head, count, ext = name.split(os.extsep)
    return (head, count, ext)


def handle_not_pickle_serializable(args):
    if isinstance(args, float):
        return float(args)
    return str(args)


class Writer(metaclass=Singleton):

    count_ofile = 0
    wrapper = inout.wrapper

    def __init__(self):
        self.parameters = inout.IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()

    def _init_ostream(self):
        if self.parameters.filename:
            self.filename = self.get_filename_path(
                self.parameters.filename)
        else:
            now = datetime.datetime.now().strftime(self.datefmt)
            filename = f"{now}{constant.pickle_ext}"
            self.filename = self.get_filename_path(filename)
        try:
            if hasattr(self, "ostream"):
                self.ostream.close()
            self.ostream = open(self.filename, "wb")
            self.count_ofile += 1
        except OSError as e:
            logger.error(f"Can't open Pickle file: {self.filename}", e)
        except Exception as e:
            logger.critical("Unexpected error", e)

    def get_filename_path(self, filename):
        utils.check_extension(filename, constant.pickle_ext)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.pickle_ext
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{filename}{os.extsep}"
                f"{self.count_ofile}{ext}")

    def write(self, function, label, args):
        try:
            to_write = {"function": function, "label": label, "args": args}
            pickle.dump(to_write, self.ostream)
        except pickle.PicklingError as e:
            logger.error(
                f"while writing in Pickle file: {self.filename}", e)
        except Exception as e:
            logger.critical("Unexpected error", e)

    def inputs(self, function, args):
        self.write(function.__name__, "inputs", args)

    def outputs(self, function, args):
        self.write(function.__name__, "outputs", args)


class Reader(metaclass=Singleton):

    def __init__(self):
        self.parameters = inout.IOInitializer()

    def read(self, filename):
        try:
            utils.check_extension(filename, constant.pickle_ext)
            logger.debug(f"Opening {filename}")
            fi = open(filename, "rb")
            data = []
            while True:
                try:
                    data.append(pickle.load(fi))
                except EOFError:
                    break
                except Exception as e:
                    logger.critical(f"Unknown exception", e)
            return data
        except OSError as e:
            logger.error(f"Can't open Pickle file: {filename}", e)
        except pickle.PicklingError as e:
            logger.error(f"While reading Pickle file: {filename}", e)
        except Exception as e:
            logger.critical("Unexpected error", e)
