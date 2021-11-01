import argparse

import pytracer.module.parser_init as parser_init
import pytracer.module.tracer_init as tracer_init
import pytracer.module.info_init as info_init
import pytracer.gui.index_init as visualize_init
import pytracer.module.clean_init as clean_init
import pytracer.module.info as pytracer_info
import pytracer.builtins

# Dynamically import module to avoid
# extra module being imported while tracing
# like importing the numpy module before tracing it


def run_trace(args):
    from pytracer.module.tracer import TracerRun
    pytracer.builtins.overload_builtins()
    pytracer_info.register.set_args(args)
    TracerRun(args).main()
    pytracer_info.register.set_trace_size()
    pytracer_info.register.register_trace()


def run_parse(args):
    from pytracer.module.parser import main
    pytracer_info.register.set_args(args)
    main(args)
    pytracer_info.register.set_aggregation_size()
    pytracer_info.register.register_aggregation()


def run_visualize(args):
    from pytracer.gui.index import main
    main(args)


def run_info(args):
    pytracer_info.PytracerInfoPrinter(args).print()


def run_clean(args):
    from pytracer.module.clean import clean
    clean()


modules = ['trace', 'parse', 'visualize', 'info', 'clean']

run_module = {
    'trace': run_trace,
    'parse': run_parse,
    'visualize': run_visualize,
    'info': run_info,
    'clean': run_clean
}

init_module = {
    'trace': tracer_init,
    'parse': parser_init,
    'visualize': visualize_init,
    'info': info_init,
    'clean': clean_init
}

_hidden_attributes = ['WrapperInstance']


def init_modules(subparser):
    for module in modules:
        init_module[module].init_module(subparser)


def pytracer_module_main(args):
    run_module[args.pytracer_module](args)


def main():
    parser = argparse.ArgumentParser(description="Pytracer", prog="pytracer")
    subparser = parser.add_subparsers(title="pytracer modules",
                                      help="pytracer modules",
                                      dest="pytracer_module")

    init_modules(subparser)

    args, _ = parser.parse_known_args()

    if args.pytracer_module:
        pytracer_module_main(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
