import pickle
import importlib

import pytracer.utils as ptutils
from pytracer.core.config import constant
from pytracer.utils.log import get_logger
from pytracer.core.config import config as cfg

from . import _init, _reader

logger = get_logger()


class ReaderPickle(_reader.Reader):

    modules_to_load = []
    are_module_imported = False

    def __init__(self, filename):
        self.filename = filename
        self.parameters = _init.IOInitializer()
        self._import_modules()
        self.__init_generator(filename)

    def _import_modules(self):
        if ReaderPickle.are_module_imported:
            return
        append = self.modules_to_load.append
        if self.modules_to_load == []:
            for module in cfg.modules_to_load:
                module_name = module.strip()
                append(module_name)
        for module in self.modules_to_load:
            importlib.import_module(module)
        ReaderPickle.are_module_imported = True

    def __init_generator(self, filename):
        try:
            ptutils.check_extension(filename, constant.pickle_ext)
            logger.debug(f"Opening {filename}", caller=self)
            fi = open(filename, "rb")
            self.unpickler = pickle.Unpickler(fi)
        except OSError as e:
            logger.error(f"Can't open Pickle file: {filename}",
                         error=e, caller=self)
        except pickle.PicklingError as e:
            logger.error(f"While reading Pickle file: {filename}",
                         error=e, caller=self)
        except Exception as e:
            logger.critical("Unexpected error",
                            error=e, caller=self)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.unpickler.load()
        except EOFError:
            raise StopIteration
        except Exception as e:
            logger.critical("Unknown exception",
                            error=e, caller=self)
