import argparse
import importlib
import os
import sys
import subprocess
from sys import prefix

from pytracer.core.config import constant
from pytracer.core.utils import color, get_human_size

excluded_directories = [".__pytracercache__", "__pycache__"]
excluded_files = ["__main__", "__init__", "generic_test"]

root_path = os.path.split(__file__)[0]
generic_test_name = "generic_test.py"
generic_test = f"{root_path}{os.sep}{generic_test_name}"

error_filename = "test.error"
error_fo = open(error_filename, "w")


def error(msg):
    print(color.red % msg, file=sys.stderr)
    sys.exit(1)


def check_args(args):

    if args.directories:
        for directory in args.directories:
            if not os.path.isdir(directory):
                error(f"{directory} is not a valid directory")

    elif args.filenames:
        for filename in args.filenames:
            if not os.path.isfile(filename):
                error(f"{filename} is not a valid file")


def list_directory(directory):

    ldir = dict()

    ls = os.listdir(directory)
    ls_prefixed = [f"{directory}{os.sep}{f}" for f in ls]

    subdirs = [get_abs(d, prefix=directory)
               for d in ls_prefixed if os.path.isdir(d)]
    subfiles = [get_abs(f, prefix=directory) for f in ls_prefixed
                if os.path.isfile(f) and os.path.splitext(f)[1] == ".py"]

    subfiles_dict = {f: get_abs(f, prefix=directory) for f in subfiles}
    subdirs_dict = {d: list_directory(
        get_abs(d, prefix=directory)) for d in subdirs}

    subdirs_dict.update(subfiles_dict)

    ldir[directory] = subdirs_dict

    return ldir


def get_abs(file, prefix=""):
    abs_file = file
    if not os.path.isabs(file):
        if prefix:
            abs_file = f"{prefix}{os.sep}{file}"
        else:
            abs_file = f"{os.getcwd()}{os.sep}{file}"
    return abs_file


def get_tests(args):

    tests = dict()

    if not args.directories and not args.filenames:
        directory = os.path.split(__file__)[0]
        tests = list_directory(directory)
    elif args.directories:
        for d in args.directories:
            dabs = get_abs(d)
            tests.update(list_directory(dabs))
    elif args.filenames:
        subfiles = {f: get_abs(f) for f in args.filenames}
        tests = {"tests": subfiles}
    else:
        error("No tests provided")

    return tests


def register_error(file):
    error_fo.write(f"{file}{os.linesep}")


def is_valid_directory(directory):
    if directory.startswith("."):
        return False

    return directory not in excluded_directories


def is_valid_file(file):
    path, name = os.path.split(file)
    name_prefix, ext = os.path.splitext(name)

    if ext == ".py" and name_prefix not in excluded_files:
        return True


def run_file(args, file):
    status = None
    if is_valid_file(file):
        stdout = open(f"{file}.stdout", "w")
        stderr = open(f"{file}.stderr", "w")
        try:
            subprocess.run(["python3", "-m", "pytracer", "--clean"])
            ret = subprocess.run(["python3", generic_test, file],
                                 check=True,
                                 stdout=stdout,
                                 stderr=stderr)
            ret.check_returncode()
            status = ret.returncode

            if args.run_parsing:
                ret = subprocess.run(["python3", "-m", "pytracer", "parse"],
                                     check=True, stderr=stderr)
                ret.check_returncode()
                status = ret.returncode

        except subprocess.CalledProcessError as e:
            register_error(file)
            status = e.returncode
    return status


def print_status(args, file, status):
    if args.show_trace_size:
        cachepath = f"{constant.cache.root}{os.sep}{constant.cache.traces}"
        trace = os.listdir(cachepath).pop()
        tracepath = f"{cachepath}{os.sep}{trace}"
        size = os.path.getsize(tracepath)
        sizeh = get_human_size(size)
        size_str = f" : {sizeh}"
    else:
        size_str = ""

    name = f"{os.path.split(file)[1]}{size_str}"
    if status is None:
        msg = color.grey % name
    elif status == 0:
        msg = color.green % name
    else:
        msg = color.red % name
    print(msg)


def run(args, tests):

    for directory, obj in tests.items():
        if obj:
            print(f"Testing files from directory {directory}")
        for name, file in obj.items():
            # Subdirectory case
            if isinstance(file, dict):
                if is_valid_directory(name):
                    run(args, file)
            elif isinstance(file, str):
                status = run_file(args, file)
                print_status(args, file, status)
            else:
                error(f"Error while parsing test directory! {file}")


def main():
    parser = argparse.ArgumentParser(description="Pytracer tests", prog="test")
    mutual_exclusion = parser.add_mutually_exclusive_group()
    mutual_exclusion.add_argument(
        "--directories", nargs="*", help="list of directories to test")
    mutual_exclusion.add_argument(
        "--filenames", nargs="*", help="list of files to test")

    parser.add_argument("--run-parsing", action="store_true",
                        help="run parsing after tracing")
    parser.add_argument("--show-trace-size", action="store_true",
                        help="Show traces size")

    args = parser.parse_args()
    check_args(args)

    tests = get_tests(args)

    print("Starting tests:")

    run(args, tests)


if __name__ == "__main__":
    main()
