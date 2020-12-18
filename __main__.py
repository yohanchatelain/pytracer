import argparse
import os

from pytracer.core.config import constant, config as cfg
from pytracer.core.tracer import init_module as pt_init_module
from pytracer.core.parser import init_module as ps_init_module
from pytracer.gui.index import init_module as pg_init_module

import shutil


def clean():
    dir_to_clean = cfg.io.cache.root
    if not dir_to_clean:
        dir_to_clean = constant.cache.root
    if os.path.isdir(dir_to_clean):
        shutil.rmtree(dir_to_clean, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Pytracer", prog="pytracer")
    parser.add_argument("--clean", action="store_true",
                        help="Clean pytracer cache path")
    subparser = parser.add_subparsers(title="pytracer modules",
                                      help="pytracer modules",
                                      dest="pytracer_module")

    pytracer_modules = dict()
    pt_init_module(subparser, pytracer_modules)
    ps_init_module(subparser, pytracer_modules)
    pg_init_module(subparser, pytracer_modules)

    args, _ = parser.parse_known_args()

    if args.clean:
        clean()
    elif args.pytracer_module:
        pytracer_modules[args.pytracer_module](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
