
import atexit
import datetime
import io
import os
import pickle
import traceback
import shutil

import pytracer.utils as ptutils
from pytracer.core.config import config as cfg
from pytracer.core.config import constant
from pytracer.utils.log import get_logger
from pytracer.utils import report
from pytracer.core.wrapper.cache import visited_files

from . import _init, _writer

logger = get_logger()


class WriterPickle(_writer.Writer):

    elements = 0
    count_ofile = 0

    def __init__(self):
        self.parameters = _init.IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()
        atexit.register(self.exit)

    def exit(self):
        # Be sure that all data in pickle buffer is dumped
        logger.debug("Close writer", caller=self)
        self.ostream.flush()
        self.ostream.close()
        if os.path.isfile(self.filename):
            if os.stat(self.filename).st_size == 0:
                os.remove(self.filename)
        self.copy_sources()

    def copy_sources(self):
        for filename in visited_files:
            src = filename
            if os.path.isfile(src):
                dst = f"{self.parameters.cache_sources_path}{os.path.sep}{filename}"
                dstdir = os.path.dirname(dst)
                os.makedirs(dstdir, exist_ok=True)
                shutil.copy(src, dst)

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
            self.pickler = pickle.Pickler(
                self.ostream, protocol=pickle.HIGHEST_PROTOCOL)
            self.pickler.fast = True
            self.count_ofile += 1
        except OSError as e:
            logger.error(f"Can't open Pickle file: {self.filename}",
                         error=e, caller=self)
        except Exception as e:
            logger.critical("Unexpected error", error=e, caller=self)

    def get_filename_path(self, filename):
        ptutils.check_extension(filename, constant.pickle_ext)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.pickle_ext
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{self.parameters.cache_traces}{os.sep}"
                f"{filename}{os.extsep}"
                f"{self.count_ofile}{ext}")

    def is_writable(self, obj):
        try:
            pickle.dump(obj, io.BytesIO())
            return True
        except Exception as e:
            try:
                obj.pop("args")
            except AttributeError:
                pass
            logger.warning(
                f"Object is not writable: {obj}", caller=self, error=e)
            return False

    def _write(self, to_write):
        self.pickler.dump(to_write)

    def write(self, **kwargs):
        function = kwargs["function"]
        time = kwargs["time"]
        module_name = kwargs["module_name"]
        function_name = kwargs["function_name"]
        label = kwargs["label"]
        args = kwargs["args"]
        backtrace = kwargs["backtrace"]

        if 'self' in args:
            args.pop('self')

        function_id = id(function)
        to_write = {"id": function_id,
                    "time": time,
                    "module": module_name,
                    "function": function_name,
                    "label": label,
                    "args": args,
                    "backtrace": backtrace}

        try:
            if self.is_writable(to_write):

                if report.report_enable():
                    key = (module_name, function_name)
                    value = to_write
                    report.report(key, value)

                if not report.report_only():
                    self._write(to_write)

            else:
                logger.warning(f"Iterate over args")
                args_ = dict()
                for name, arg in args.items():
                    if not self.is_writable(arg):
                        args_[name] = None
                    else:
                        args_[name] = arg

                to_write['args'] = args_
                if report.report_enable():
                    key = (module_name, function_name)
                    value = to_write
                    report.report(key, value)

                if not report.report_only():
                    self._write(to_write)

        except pickle.PicklingError as e:
            logger.error(
                f"while writing in Pickle file: {self.filename}",
                error=e, caller=self)
        except (AttributeError, TypeError) as e:
            logger.warning(
                f"Unable to pickle object: {args}", caller=self, error=e)
        except Exception as e:
            logger.debug(f"Writing pickle object: {to_write}", caller=self)
            logger.critical("Unexpected error while writing",
                            error=e, caller=self)

    def inputs(self, **kwargs):
        self.write(**kwargs, label="inputs")

    def module_name(self, obj):
        module = getattr(obj, "__module__", "")
        if not module and hasattr(module, "__class__"):
            module = getattr(obj.__class__, "__module__")
        return module

    def inputs_instance(self, **kwargs):
        function = kwargs.pop("instance")
        function_name = getattr(function, "__name__", "")
        module_name = self.module_name(function)
        self.write(**kwargs,
                   function=function,
                   function_name=function_name,
                   module_name=module_name,
                   label="inputs")

    def outputs(self, **kwargs):
        self.write(**kwargs, label="outputs")

    def outputs_instance(self, **kwargs):
        function = kwargs.pop("instance")
        function_name = getattr(function, "__name__", "")
        module_name = self.module_name(function)
        self.write(**kwargs,
                   function=function,
                   function_name=function_name,
                   module_name=module_name,
                   label="outputs")

    def backtrace(self):
        if cfg.io.backtrace:
            stack = traceback.extract_stack(limit=4)[0]
            visited_files.add(stack.filename)
            return stack
        return None
