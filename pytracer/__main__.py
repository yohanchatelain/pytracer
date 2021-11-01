import argparse
import os
import shutil

import pytracer.module.parser_init as parser_init
import pytracer.module.tracer_init as tracer_init
import pytracer.module.info_init as info_init
import pytracer.gui.index_init as visualize_init
import pytracer.module.clean_init as clean_init
from pytracer.core.config import config as cfg
from pytracer.core.config import constant
import pytracer.module.info as pytracer_info
import pytracer.builtins
import pytracer.cache


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
        from pytracer.module.tracer import TracerRun
        pytracer.builtins.overload_builtins()
        pytracer_info.register.set_args(args)
        pytracer.cache.set_module_args(args)
        TracerRun(args).main()
        pytracer_info.register.set_trace_size()
        pytracer_info.register.register_trace()
    elif args.pytracer_module == "parse":
        from pytracer.module.parser import main
        pytracer_info.register.set_args(args)
        pytracer.cache.set_module_args(args)
        main(args)
        pytracer_info.register.set_aggregation_size()
        pytracer_info.register.register_aggregation()
    elif args.pytracer_module == "visualize":
        from pytracer.gui.index import main
        pytracer.cache.set_module_args(args)
        main(args)
    elif args.pytracer_module == "info":
        pytracer_info.PytracerInfoPrinter(args).print()
    elif args.pytracer_module == "clean":
        clean()


def main():
    parser = argparse.ArgumentParser(description="Pytracer", prog="pytracer")
    subparser = parser.add_subparsers(title="pytracer modules",
                                      help="pytracer modules",
                                      dest="pytracer_module")

    tracer_init.init_module(subparser)
    parser_init.init_module(subparser)
    visualize_init.init_module(subparser)
    info_init.init_module(subparser)
    clean_init.init_module(subparser)

    args, _ = parser.parse_known_args()

    if args.pytracer_module:
        pytracer_module_main(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
