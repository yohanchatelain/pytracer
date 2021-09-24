from pytracer.utils.singleton import Singleton
import os
import csv
import sys
from enum import Enum, auto
from pytracer.utils.memory import total_size
from pytracer.utils import get_filename
from pytracer.core.config import constant


class Report(metaclass=Singleton):

    class ReportOption(Enum):
        ON = auto()
        OFF = auto()
        ONLY = auto()

    report_option_default = ReportOption.OFF.name
    report_options = [x.lower() for x in ReportOption.__members__.keys()]

    def __init__(self, option, filename):
        self.set_report(option)
        if self.report_enable():
            self._report_type = None
            self._report_call_dict = {}
            self._report_memory_dict = {}
            self._init_filename(filename)
        else:
            self._report_filename = None

    def _init_filename(self, filename):
        if filename == '':
            filename = constant.report_filename
        self._report_filename = get_filename(filename)
        self._report_ostream = open(self._report_filename, 'w')

    def get_filename(self):
        return self._report_filename

    def get_filename_path(self):
        abspath = f"{os.getcwd()}{os.path.sep}{self._report_filename}"
        return abspath if self._report_filename else None

    def set_filename(self, filename):
        self._report_filename = filename

    def set_report(self, report_str):
        lwc = report_str.lower()
        if lwc == Report.ReportOption.ON.name.lower():
            self._report_type = Report.ReportOption.ON
        elif lwc == Report.ReportOption.OFF.name.lower():
            self._report_type = Report.ReportOption.OFF
        elif lwc == Report.ReportOption.ONLY.name.lower():
            self._report_type = Report.ReportOption.ONLY
        else:
            sys.exit("Wrong report type")

    def report_enable(self):
        return self._report_type != Report.ReportOption.OFF

    def report_only(self):
        return self._report_type == Report.ReportOption.ONLY

    def increment_call_report(self, key):
        if key in self._report_call_dict:
            self._report_call_dict[key] += 1
        else:
            self._report_call_dict[key] = 1

    def increment_memory_report(self, key, memory):
        if key in self._report_memory_dict:
            self._report_memory_dict[key] += memory
        else:
            self._report_memory_dict[key] = memory

    def report(self, key, value):
        self.increment_call_report(key)
        sizeof = total_size(value)
        self.increment_memory_report(key, sizeof)

    def dump_report(self):
        fieldnames = ["module", "function", "call", "memory"]

        writer = csv.DictWriter(self._report_ostream, fieldnames=fieldnames)
        writer.writeheader()
        total_call = 0
        total_memory = 0
        for key, call in self._report_call_dict.items():
            module, function = key
            memory = self._report_memory_dict[key]
            total_call += call/2
            total_memory += memory
            row = {"module": module, "function": function,
                   "call": call/2, "memory": memory}
            writer.writerow(row)
        total_row = {"module": "Total",
                     "function": "Total",
                     "call": total_call,
                     "memory": total_memory}
        writer.writerow(total_row)
