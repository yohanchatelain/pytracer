import atexit
import datetime
import logging
import os
import sys
from abc import abstractmethod
from enum import IntEnum, auto

import pytracer.core.utils.color as color
import pytracer.core.utils.singleton as singleton
from pytracer.core.config import config as cfg

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
    def debug(self, msg, caller=None):
        pass

    @ abstractmethod
    def info(self, msg, caller=None):
        pass

    @ abstractmethod
    def warning(self, msg, caller=None, error=None):
        pass

    @ abstractmethod
    def error(self, msg, caller=None, error=None):
        pass

    @ abstractmethod
    def critical(self, msg, caller=None, error=None):
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

    def init(self):
        self.date = datetime.datetime.now
        self.time = lambda: self.date().strftime(self.parameters.datefmt)

    def start(self):
        self.info("--Start--")

    def end(self):
        self.flush()
        self.info("--End--")

    def flush(self):
        self.parameters.ostream.flush()

    def _print(self, level, caller, msg, ostream=None):
        if self.parameters.level > level:
            return

        if caller:
            scaller = getattr(caller, "__class__", "")
            scaller = getattr(scaller, "__name__", "")
            scaller = f"[{scaller}]" if scaller else scaller
        else:
            scaller = ""

        if self.parameters.color:
            color_level = self._color_level[level]
            _time = color.white % f"{self.time()}"
            _level = color_level % level.name
            _msg = color.grey_dark_40 % msg
            _caller = color.grey_dark_40 % scaller
        else:
            _time = f"{self.time()}"
            _level = level.name
            _msg = msg
            _caller = scaller
        header = f"[{_time}] {_level}"

        to_print = f"{header}: {_caller} {_msg}{os.linesep}"
        if ostream:
            ostream.write(to_print)
        self.parameters.ostream.write(to_print)

    def debug(self, msg, caller=None):
        self._print(Level.DEBUG, caller, msg)

    def info(self, msg, caller=None):
        self._print(Level.INFO, caller, msg)

    def warning(self, msg, caller=None, error=None):
        self._print(Level.WARNING, caller, msg, ostream=sys.stderr)
        if error:
            self._print(Level.WARNING, caller, error, ostream=sys.stderr)

    def error(self, msg, caller=None, error=None):
        self._print(Level.ERROR, caller, msg, ostream=sys.stderr)
        if error:
            self._print(Level.ERROR, caller, error, ostream=sys.stderr)
        sys.exit(1)

    def critical(self, msg, caller=None, error=None):
        self._print(Level.CRITICAL, caller, msg, ostream=sys.stderr)
        if error:
            self._print(Level.CRITICAL, caller, error, ostream=sys.stderr)
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
        logging.basicConfig(format="[%(asctime)s]%(levelname)s:%(message)s",
                            datefmt=self.parameters.datefmt,
                            stream=self.parameters.ostream,
                            level=logging.DEBUG)

    def start(self):
        self.info("--Start--")

    def end(self):
        self.flush()
        self.info("--End--")

    def __del__(self):
        self.end()

    def _caller_str(self, caller):
        if caller:
            scaller = getattr(caller, "__class__", "")
            scaller = getattr(caller, "__name__", "")
            return f"[{scaller}] " if scaller else scaller
        return ""

    def flush(self):
        pass

    def debug(self, msg, caller=None):
        _msg = self._caller_str(caller) + str(msg)
        logging.debug(_msg)

    def info(self, msg, caller=None):
        _msg = self._caller_str(caller) + str(msg)
        logging.info(_msg)

    def warning(self, msg, caller=None, error=None):
        _msg = self._caller_str(caller) + str(msg)
        logging.warning(_msg)
        if error:
            logging.warning(error)

    def error(self, msg, caller=None, error=None):
        _msg = self._caller_str(caller) + str(msg)
        logging.error(_msg)
        if error:
            logging.error(error)
            self.end()
            raise error
        self.end()
        sys.exit(1)

    def critical(self, msg, caller=None, error=None):
        _msg = self._caller_str(caller) + str(msg)
        logging.critical(_msg)
        if error:
            logging.critical(error)
            self.end()
            raise error
        self.end()
        sys.exit(2)


def get_logger():
    loginit = LogInitializer()
    if loginit.get_type() == Type.PRINT:
        return LogPrint()
    if loginit.get_type() == Type.LOGGER:
        return LogLogger()
    sys.exit(f"Bad log type: {loginit.get_type()}")
