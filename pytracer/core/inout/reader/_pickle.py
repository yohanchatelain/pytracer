import pickle
import sys
import importlib

import pytracer.core.utils as ptutils
from pytracer.core.config import constant
from pytracer.core.utils.log import get_logger
from pytracer.core.config import config as cfg

from . import _init, _reader

logger = get_logger()


class ReaderPickle(_reader.Reader):

    modules_to_load = list()

    def __init__(self):
        self.parameters = _init.IOInitializer()
        self._import_modules()

    def _import_modules(self):
        if self.modules_to_load == []:
            for module in cfg.modules_to_load:
                module_name = module.strip()
                self.modules_to_load.append(module_name)
        for module in self.modules_to_load:
            importlib.import_module(module)

    def read(self, filename):
        try:
            ptutils.check_extension(filename, constant.pickle_ext)
            logger.debug(f"Opening {filename}", caller=self)
            fi = open(filename, "rb")
            unpickler = pickle.Unpickler(fi)
            data = []
            i = 0
            while True:
                try:
                    _obj = unpickler.load()
                    data.append(_obj)
                except EOFError:
                    break
                except Exception as e:
                    logger.critical("Unknown exception",
                                    error=e, caller=self)
            return data
        except OSError as e:
            logger.error(f"Can't open Pickle file: {filename}",
                         error=e, caller=self)
        except pickle.PicklingError as e:
            logger.error(f"While reading Pickle file: {filename}",
                         error=e, caller=self)
        except Exception as e:
            logger.critical("Unexpected error",
                            error=e, caller=self)
