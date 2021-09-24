import argparse
from atexit import register
import os
import shutil

import pytracer.core.parser_init as parser_init
import pytracer.core.tracer_init as tracer_init
import pytracer.core.info_init as info_init
import pytracer.gui.index_init as visualize_init
from pytracer.core.config import config as cfg
from pytracer.core.config import constant
import pytracer.core.info as pytracer_info


def clean():
    dir_to_clean = cfg.io.cache.root
    if not dir_to_clean:
        dir_to_clean = constant.cache.root
    if os.path.isdir(dir_to_clean):
        shutil.rmtree(dir_to_clean, ignore_errors=True)

# Dynamically import module to avoid
# extra module being imported while tracing
# like importing the numpy module before tracing it


def pytracer_module_main(args):
    if args.pytracer_module == "trace":
        from pytracer.core.tracer import TracerRun
        pytracer_info.register.set_args(args)
        TracerRun(args).main()
        pytracer_info.register.set_trace_size()
        pytracer_info.register.register_trace()
    elif args.pytracer_module == "parse":
        from pytracer.core.parser import main
        pytracer_info.register.set_args(args)
        main(args)
        pytracer_info.register.set_aggregation_size()
        pytracer_info.register.register_aggregation()
    elif args.pytracer_module == "visualize":
        from pytracer.gui.index import main
        main(args)
    elif args.pytracer_module == "info":
        pytracer_info.PytracerInfoPrinter(args).print()


def main():
    parser = argparse.ArgumentParser(description="Pytracer", prog="pytracer")
    parser.add_argument("--clean", action="store_true",
                        help="Clean pytracer cache path")
    subparser = parser.add_subparsers(title="pytracer modules",
                                      help="pytracer modules",
                                      dest="pytracer_module")

    tracer_init.init_module(subparser)
    parser_init.init_module(subparser)
    visualize_init.init_module(subparser)
    info_init.init_module(subparser)

    args, _ = parser.parse_known_args()

    if args.clean:
        clean()
    elif args.pytracer_module:
        pytracer_module_main(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
