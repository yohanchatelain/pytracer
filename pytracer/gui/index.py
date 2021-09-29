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
    enable_timer = False

    if enable_timer:
        print("STARTING")
        start = time.time()

    import pytracer.gui.callbacks
    from pytracer.gui.app import app

    init_layout(app, args)
    pgc.init_data(args)

    if enable_timer:
        end = time.time()
        print(f"DONE in time: {end - start}")

    print("Threaded:", args.threaded)

    app.run_server(debug=args.debug, threaded=args.threaded, host=args.host)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Pytracer visualization module")
    subparser = parser.add_subparsers()
    index_init.init_module(subparser)
    args = parser.parse_args()
    main(args)
