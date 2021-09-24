import pytracer.utils.report as report


def init_arguments(parser):
    parser.add_argument("--module", required=True,
                        help="path of the module to trace")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the module wihtout tracing it")
    parser.add_argument("--report", choices=report.Report.report_options,
                        default=report.Report.report_option_default,
                        help="Report call and memory usage")
    parser.add_argument("--report-file", default='', metavar="FILE",
                        help="Write report to <FILE>")


def init_module(subparser):
    tracer_parser = subparser.add_parser("trace", help="trace functions")
    init_arguments(tracer_parser)
