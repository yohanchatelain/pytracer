import atexit
import datetime
import logging
import os
import sys
from abc import abstractmethod
from enum import IntEnum, auto

from config import PytracerError
from config import config as cfg

import utils.color as color
import utils.singleton as singleton

logger_filename = "pytracer.log"


class Type(IntEnum):
    PRINT = auto()
    LOGGER = auto()


class Level(IntEnum):
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


def level_from_str(level):
    try:
        return Level[level.upper()]
    except (KeyError, AttributeError):
        return None


class LogInitializer(metaclass=singleton.Singleton):

    ofilename_default = "pytracer.log"
    type_default = Type.LOGGER
    level_default = Level.INFO

    def __init__(self):
        self.datefmt = "%H:%M:%S"
        self.read_parameters()

    def read_parameters(self):
        fmt = cfg.logger.format
        if fmt:
            if fmt.lower() == "print":
                self.type = Type.PRINT
            elif fmt.lower() == "logger":
                self.type = Type.LOGGER
        else:
            self.type = self.type_default

        output = cfg.logger.output
        if output:
            if output == "stdout":
                self.ofilename = "<stdout>"
                self.ostream = sys.stdout
            else:
                self.ofilename = output
                self.ostream = open(self.ofilename, "w")
        else:
            self.ofilename = self.ofilename_default
            self.ostream = open(self.ofilename, "w")

        self.color = cfg.logger.color
        _level = level_from_str(cfg.logger.level)
        if _level:
            self.level = _level
        else:
            self.level = self.level_default

    def get_type(self):
        return self.type


class Log(metaclass=singleton.Singleton):

    def __init__(self):
        self.parameters = LogInitializer()

    @ abstractmethod
    def start(self):
        pass

    @ abstractmethod
    def stop(self):
        pass

    @ abstractmethod
    def debug(self, msg):
        pass

    @ abstractmethod
    def info(self, msg):
        pass

    @ abstractmethod
    def warning(self, msg, error=None):
        pass

    @ abstractmethod
    def error(self, msg, error=None):
        pass

    @ abstractmethod
    def critical(self, msg, error=None):
        pass


class LogPrint(Log):

    _color_level = {
        Level.DEBUG: color.grey,
        Level.INFO: color.blue,
        Level.WARNING: color.yellow,
        Level.ERROR: color.orange,
        Level.CRITICAL: color.red
    }

    def __init__(self):
        super().__init__()
        self.type = Type.PRINT
        self.init()
        self.start()
        atexit.register(self.end)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.end()

    def init(self):
        self.date = datetime.datetime.now()
        self.time = self.date.strftime(self.parameters.datefmt)

    def start(self):
        self.info("--Start--")

    def end(self):
        self.info("--End--")

    def _print(self, level, msg):
        if self.parameters.level > level:
            return

        if self.parameters.color:
            color_level = self._color_level[level]
            _time = color.white % f"{self.time}"
            _level = color_level % level.name
            _msg = color.grey_dark_40 % msg
        else:
            _time = f"{self.time}"
            _level = level.name
            _msg = msg
        header = f"[{_time}] {_level}"
        self.parameters.ostream.write(f"{header}: {_msg}{os.linesep}")

    def debug(self, msg):
        self._print(Level.DEBUG, msg)

    def info(self, msg):
        self._print(Level.INFO, msg)

    def warning(self, msg, error=None):
        self._print(Level.WARNING, msg)
        if error:
            self._print(Level.WARNING, error)

    def error(self, msg, error=None):
        self._print(Level.ERROR, msg)
        if error:
            self._print(Level.ERROR, error)
            raise error
        sys.exit(1)

    def critical(self, msg, error=None):
        self._print(Level.CRITICAL, msg)
        if error:
            self._print(Level.CRITICAL, error)
            raise error
        sys.exit(2)


class LogLogger(Log):

    def __init__(self):
        super().__init__()
        self.init()
        self.start()
        atexit.register(self.stop)

    def init(self):
        self.type = Type.LOGGER
        logging.basicConfig(format="[%(ascitime)s]%(levelname)s:%(message)s",
                            datefmt=self.parameters.datefmt,
                            stream=self.parameters.ostream,
                            style="{",
                            level=logging.DEBUG)

    def start(self):
        self.info("--Start--")

    def end(self):
        self.info("--End--")

    def __del__(self):
        self.end()

    def debug(self, msg):
        logging.debug(msg)

    def info(self, msg):
        logging.info(msg)

    def warning(self, msg, error=None):
        logging.warning(msg)
        if error:
            logging.warning(error)

    def error(self, msg, error=None):
        logging.error(msg)
        if error:
            logging.error(error)
        sys.exit(1)

    def critical(self, msg, error=None):
        logging.critical(msg)
        if error:
            logging.critical(error)
            raise error
        sys.exit(2)


def get_log():
    loginit = LogInitializer()
    if loginit.get_type() == Type.PRINT:
        return LogPrint()
    if loginit.get_type() == Type.LOGGER:
        return LogLogger()
    sys.exit(f"Bad log type: {loginit.get_type()}")
