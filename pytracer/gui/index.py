import argparse
from pytracer.gui.layout import get_rootpanel

import dash_core_components as dcc
import dash_html_components as html

import pytracer.gui.core as pgc
import pytracer.gui.index_init as index_init
import time
import cProfile
import pstats


def init_layout(app, args):
    from pytracer.gui.layout import header, modal, get_rootpanel, sidebar
    app.layout = html.Div([
        html.Div(id="output-clientsid"),
        header,
        modal,
        html.Div(
            [
                sidebar,
                get_rootpanel(args)
            ],
            style={"display": "flex", "flex-direction": "row", 'width': '100%'}
        ),
    ], style={"display": "flex", "flex-direction": "column", 'width': '100%'},
        className='container')


def main(args):
    print("STARTING")
    start = time.time()
    # pr = cProfile.Profile()
    # pr.enable()

    import pytracer.gui.callbacks
    from pytracer.gui.app import app

    init_layout(app, args)
    pgc.init_data(args)

    end = time.time()
    print(f"DONE in time: {end - start}")

    print("Threaded:", args.threaded)

    app.run_server(debug=args.debug, threaded=args.threaded, host=args.host)
    # pr.disable()
    # pr.print_stats(sort="cumtime")
    # pr.dump_stats("output.prof")
    #
    # stream = open('output.txt', 'w')
    # stats = pstats.Stats('output.prof', stream=stream)
    # stats.sort_stats('cumtime')
    # stats.print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Pytracer visualization module")
    subparser = parser.add_subparsers()
    index_init.init_module(subparser)
    args = parser.parse_args()
    main(args)
