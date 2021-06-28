import os
import csv
import sys
from enum import Enum, auto
from pytracer.utils.memory import total_size


class Report(Enum):
    ON = auto()
    OFF = auto()
    ONLY = auto()


_report_type = None
_report_call_dict = {}
_report_memory_dict = {}


report_type_default = Report.OFF.name
report_type = list(map(lambda x: x.lower(), Report.__members__.keys()))


def set_report(report_str):
    global _report_type
    lwc = report_str.lower()
    if lwc == Report.ON.name.lower():
        _report_type = Report.ON
    elif lwc == Report.OFF.name.lower():
        _report_type = Report.OFF
    elif lwc == Report.ONLY.name.lower():
        _report_type = Report.ONLY
    else:
        sys.exit("Wrong report type")


def report_enable():
    return _report_type != Report.OFF


def report_only():
    return _report_type == Report.ONLY


def increment_call_report(key):
    if key in _report_call_dict:
        _report_call_dict[key] += 1
    else:
        _report_call_dict[key] = 1


def increment_memory_report(key, memory):
    if key in _report_memory_dict:
        _report_memory_dict[key] += memory
    else:
        _report_memory_dict[key] = memory


def report(key, value):
    increment_call_report(key)
    sizeof = total_size(value)
    increment_memory_report(key, sizeof)


def get_filename(basename):
    i = 0
    filename = basename
    while os.path.isfile(filename):
        filename = f"{basename}.{i}"
        i += 1
    return filename


def dump_report():
    fieldnames = ["module", "function", "call", "memory"]

    report_filename = get_filename("report.csv")

    with open(report_filename, "w") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        total_call = 0
        total_memory = 0
        for key, call in _report_call_dict.items():
            module, function = key
            memory = _report_memory_dict[key]
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
