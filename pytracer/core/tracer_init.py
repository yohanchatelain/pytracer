from pytracer.core.utils.report import report_type, report_type_default


def init_arguments(parser):
    parser.add_argument("--module", required=True,
                        help="path of the module to trace")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the module wihtout tracing it")
    parser.add_argument("--report", choices=report_type,
                        default=report_type_default,
                        help="Report call and memory usage")


def init_module(subparser):
    tracer_parser = subparser.add_parser("trace", help="trace functions")
    init_arguments(tracer_parser)
