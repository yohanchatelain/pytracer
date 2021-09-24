import atexit
from datetime import datetime
import h5py

import pytracer.core.inout as ptinout
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Singleton
from pytracer.core.config import constant, config as cfg

logger = get_logger()


class Writer(metaclass=Singleton):

    wrapper = ptinout.wrapper
    wrapper_class = ptinout.wrapper_class
    wrapper_instance = ptinout.wrapper_instance

    def __init__(self):
        self.parameters = ptinout.IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()
        atexit.register(self.exit)

    def exit(self):
        logger.debug("Close writer", caller=self)
        self.ostream.close()

    def _init_ostream(self):
        if self.parameters.filename:
            self.filename = self.get_filename_path(self.parameters.filename)
        else:
            now = datetime.now().strftime(self.datefmt)
            filename = f"{now}{constant.extension.hdf5}"
            self.filename = self.get_filename_path(filename)

        self.ostream = h5py.File(self.filename, "w")
