
import atexit
import collections
import datetime
import inspect
import io
import os
import pickle
import shutil
import threading
import traceback
import types
from collections import deque
from contextlib import contextmanager

import pytracer.cache as cache
import pytracer.core.inout._init as _init
import pytracer.core.inout.binding as binding
import pytracer.utils as ptutils
from pytracer.cache import dumped_functions, visited_files
from pytracer.core.config import config as cfg
from pytracer.core.config import constant
from pytracer.utils import get_functions_from_traceback, report
from pytracer.utils.log import get_logger
from pytracer.utils.singleton import Counter

from . import _writer

logger = get_logger()

lock = threading.Lock()

elements = Counter()


def increment_visit(module, function):
    if (key := f"{module}.{function}") in dumped_functions:
        dumped_functions[key] += 1
    else:
        dumped_functions[key] = 1


class PytracerPickler(pickle.Pickler):

    def reducer_override(self, obj):
        if hasattr(obj, 'generic_wrapper'):
            d = (types.FunctionType, obj.__name__, {
                 k: v for k, v in obj.__dict__.items() if k != 'generic_wrapper'})
            return d
        else:
            return NotImplemented

    def dumps(self, obj):
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)


class PytracerPickleTrace(dict):

    def __str__(self):
        d = {k: self[k] for k in self if k != 'args'}
        return str(d)

    def __repr__(self):
        d = {k: self[k] for k in self if k != 'args'}
        return repr(d)


@contextmanager
def safe_dump(self, pickler):
    if self.is_dumping:
        return
    self.is_dumping = True
    try:
        yield pickler
    except Exception as e:
        logger.warning(f'Pickle object cannot be saved', caller=self, error=e)
    finally:
        self.is_dumping = False


class WriterPickle(_writer.Writer):

    elements = 0
    count_ofile = 0

    def __init__(self):
        self.is_dumping = False
        self.parameters = _init.IOInitializer()
        self.datefmt = "%y%m%d%H%M%S"
        self._init_ostream()
        atexit.register(self.exit)

    def exit(self):
        # Be sure that all data in pickle buffer is dumped
        logger.debug("Close writer", caller=self)
        self.ostream.flush()
        self.ostream.close()
        if os.path.isfile(self.filename_path):
            if os.stat(self.filename_path).st_size == 0:
                os.remove(self.filename_path)
        self.copy_sources()

    def get_filename(self):
        return self.filename

    def get_filename_path(self):
        return self.filename_path

    def copy_sources(self):
        for filename in visited_files:
            src = filename
            if os.path.isfile(src):
                dst = f"{self.parameters.cache_sources_path}{os.path.sep}{filename}"
                dstdir = os.path.dirname(dst)
                os.makedirs(dstdir, exist_ok=True)
                shutil.copy(src, dst)

    def _init_streams(self):
        try:
            self.ostream = open(self.filename_path, "wb")
            self.pickler = PytracerPickler(
                self.ostream, protocol=pickle.HIGHEST_PROTOCOL)
            # self.pickler = pickle.Pickler(
            #     self.ostream, protocol=pickle.HIGHEST_PROTOCOL)
            self.pickler.fast = True
        except OSError as e:
            logger.error(f"Can't open pickle file: {self.filename_path}",
                         error=e, caller=self, raise_error=False)
        except Exception as e:
            logger.critical("Unexpected error", error=e, caller=self)

    def _init_ostream(self):
        if not (filename := self.parameters.trace):
            filename = datetime.datetime.now().strftime(self.datefmt)
        self.filename = ptutils.get_filename(
            filename, constant.extension.pickle)
        self.filename_path = self._get_filename_path(self.filename)

        self._init_streams()

    def _get_filename_path(self, filename):
        ptutils.check_extension(filename, constant.extension.pickle)
        filename, ext = os.path.splitext(filename)
        ext = ext if ext else constant.extension.pickle
        return (f"{self.parameters.cache_path}{os.sep}"
                f"{self.parameters.cache_traces}{os.sep}"
                f"{filename}{ext}")

    # def is_looping(self):

    #     def aux(stack):
    #         return '/pytracer/core' in stack.filename and stack.function == 'write'
    #     return sum(map(aux, inspect.stack())) >= 2

    # def is_writable(self, obj):
    #     if self.is_looping():
    #         return False
    #     try:
    #         pickle.dump(obj, io.BytesIO())
    #         return True
    #     except Exception as e:
    #         try:
    #             obj["args"] = {}
    #         except (AttributeError, KeyError, TypeError):
    #             pass
    #         logger.warning(
    #             f"Object is not writable: {obj}", caller=self, error=e)
    #         return False
    def is_writable(self, obj):
        if self.is_dumping:
            return False
        self.is_dumping = True
        try:
            pickle.dump(obj, io.BytesIO(),
                        protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            print(e)
            self.is_dumping = False
            return False
        else:
            self.is_dumping = False
            return True

    def _dump(self, obj):
        if self.is_dumping:
            return False
        self.is_dumping = True
        try:
            self.pickler.dump(obj)
        except Exception:
            self.is_dumping = False
        else:
            self.is_dumping = False

    def _write(self, to_write):
        self._dump(to_write)
        # self.pickler.dump(to_write)

    def critical_writing_error(self, e):
        possible_functions = get_functions_from_traceback()
        msg = "Possible functions responsible for the issue:\n"
        msg += "\n".join([f"\t{f}" for f in possible_functions])
        msg += "\nTry again, excluding them\n"
        cache.cached_error = (msg, e)
        raise e

        # logger.critical(f"{msg}Unexpected error while writing",
        #                 error=e, caller=self)

    def clean_args(self, args):
        keys = list(args.keys())
        for name in keys:
            if name == 'self':
                args.pop(name)
            elif not self.is_writable(args[name]):
                args.pop(name)
            else:
                continue

    def dump(self, **kwargs):
        module_name = kwargs["module_name"]
        if module_name in ('posix', 'posixpath'):
            return

    # def clean_args(self, args):

    #     keys = list(args.keys())

    #     for name in keys:
    #         if name == 'self' or not self.is_writable(args[name]):
    #             args.pop(name)

    #     return args

    # def write(self, **kwargs):
        function = kwargs["function"]
        time = kwargs["time"]
        # module_name = kwargs["module_name"]
        function_name = kwargs["function_name"]
        label = kwargs["label"]
        args = kwargs["args"]
        backtrace = kwargs["backtrace"]

        increment_visit(module_name, function_name)

        self.clean_args(args)

        function_id = id(function)
        # to_write = {"id": function_id,
        #             "time": time,
        #             "module": module_name,
        #             "function": function_name,
        #             "label": label,
        #             "args": args,
        #             "backtrace": backtrace}

        to_write = PytracerPickleTrace(id=function_id,
                                       time=time,
                                       module=module_name,
                                       function=function_name,
                                       label=label,
                                       args=args,
                                       backtrace=backtrace)

        logger.debug((f"id: {function_id}\n"
                      f"time: {time}\n"
                      f"module: {module_name}\n"
                      f"function: {function_name}\n"
                      f"label: {label}\n"
                      f"backtrace: {backtrace}\n"), caller=self)

        # if lock.locked():
        #     return
        # lock.acquire()
        try:
            if not self.is_writable(to_write):
                to_write['args'] = {}

            if report.report.report_enable():
                key = (module_name, function_name)
                value = to_write
                report.report.report(key, value)

            if not report.report.report_only():
                self._write(to_write)

        except Exception as e:
            logger.warning(
                f"Unable to pickle object for {function_name}", caller=self, error=e)
            if report.report.report_enable():
                key = (module_name, function_name)
                value = to_write
                report.report.report(key, value)
            if not report.report.report_only():
                to_write['args'] = {}
                self._write(to_write)

        # except pickle.PicklingError as e:
        #     logger.error(
        #         f"while writing in Pickle file: {self.filename_path}",
        #         error=e, caller=self)
        # except (AttributeError, TypeError) as e:
        #     logger.warning(
        #         f"Unable to pickle object: {args} {function_name}", caller=self, error=e)
        #     if report.report_enable():
        #         key = (module_name, function_name)
        #         value = to_write
        #         report.report(key, value)
        #     if not report.report_only():
        #         to_write['args'] = {}
        #         self._write(to_write)
        # except Exception as e:
        #     logger.debug(f"Writing pickle object: {to_write}", caller=self)
        #     self.critical_writing_error(e)
        # lock.release()

    def inputs(self, **kwargs):
        self.dump(**kwargs, label="inputs")
        # self.write(**kwargs, label="inputs")

    def module_name(self, obj):
        module = getattr(obj, "__module__", "")
        if not module and hasattr(module, "__class__"):
            module = getattr(obj.__class__, "__module__")
        return module

    def inputs_instance(self, **kwargs):
        function = kwargs.pop("instance")
        function_name = getattr(function, "__name__", "")
        module_name = self.module_name(function)
        self.dump(**kwargs,
                  function=function,
                  function_name=function_name,
                  module_name=module_name,
                  label="inputs")

        # self.write(**kwargs,
        #            function=function,
        #            function_name=function_name,
        #            module_name=module_name,
        #            label="inputs")

    def outputs(self, **kwargs):
        self.dump(**kwargs, label="outputs")

        # self.write(**kwargs, label="outputs")

    def outputs_instance(self, **kwargs):
        function = kwargs.pop("instance")
        function_name = getattr(function, "__name__", "")
        module_name = self.module_name(function)
        self.dump(**kwargs,
                  function=function,
                  function_name=function_name,
                  module_name=module_name,
                  label="outputs")
        # self.write(**kwargs,
        #            function=function,
        #            function_name=function_name,
        #            module_name=module_name,
        #            label="outputs")

    def backtrace(self):
        if cfg.io.backtrace:
            stack = traceback.extract_stack(limit=4)[0]
            visited_files.add(stack.filename)
            return stack
        return None

    def write(self, function, module, name, *args, **kwargs):

        bind = binding.Binding(function, *args, **kwargs)
        stack = self.backtrace()

        time = elements()

        self.inputs(time=time,
                    module_name=module,
                    function_name=name,
                    function=function,
                    args=bind.arguments,
                    backtrace=stack)

        try:
            outputs = function(*bind.args, **bind.kwargs)
        except Exception as e:
            self.critical_writing_error(e)

        _outputs = binding.format_output(outputs)

        self.outputs(time=time,
                     module_name=module,
                     function_name=name,
                     function=function,
                     args=_outputs,
                     backtrace=stack)

        return outputs

    def write_instance(self, instance, function, module, *args, **kwargs):

        bind = binding.Binding(function, *args, **kwargs)
        stack = self.backtrace()

        time = elements()

        self.inputs(time=time,
                    module_name=module,
                    function_name=function,
                    function=function,
                    args=bind.arguments,
                    backtrace=stack)

        try:
            outputs = getattr(getattr(instance, '__class__'),
                              function)(instance, *args, **kwargs)
        except Exception as e:
            self.critical_writing_error(e)

        _outputs = binding.format_output(outputs)

        self.outputs(time=time,
                     module_name=module,
                     function_name=function,
                     function=function,
                     args=_outputs,
                     backtrace=stack)

        return outputs

    def write_function(self,
                       info,
                       *args, **kwargs):

        fid, fmodule, fname = info
        function = cache.id_dict[fid]

        bind = binding.Binding(function, *args, **kwargs)
        stack = self.backtrace()

        time = elements()

        self.inputs(time=time,
                    module_name=fmodule,
                    function_name=fname,
                    function=function,
                    args=bind.arguments,
                    backtrace=stack)

        try:
            outputs = function(*bind.args, **bind.kwargs)
        except Exception as e:
            self.critical_writing_error(e)

        _outputs = format_output(outputs)

        self.outputs(time=time,
                     module_name=fmodule,
                     function_name=fname,
                     function=function,
                     args=_outputs,
                     backtrace=stack)

        return outputs


def format_output(outputs):
    if isinstance(outputs, dict):
        _dict = {k: v for k, v in outputs.items() if not k.startswith('__')
                 and not k.endswith('__')}
        _outputs = _dict
    elif isinstance(outputs, tuple):
        _outputs = {f"Ret{i}": o for i, o in enumerate(outputs)}
    else:
        _outputs = {"Ret": outputs}
    return _outputs
