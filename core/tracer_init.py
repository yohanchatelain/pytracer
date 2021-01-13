def init_arguments(parser):
    parser.add_argument("--module", required=True,
                        help="path of the module to trace")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the module wihtout tracing it")


def init_module(subparser):
    tracer_parser = subparser.add_parser("trace", help="trace functions")
    init_arguments(tracer_parser)
