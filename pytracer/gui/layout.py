
from dash_core_components.Input import Input
from dash_html_components.Label import Label
import dash_ace
import dash_core_components as dcc
import dash_html_components as html
import dash_table as dt
import dash_daq as daq
import plotly.express as px

import pytracer.gui.core as pgc
import pytracer.callgraph.core as pcc

# TODO: Use regexp to get original module
# >>> c=re.compile(r"[a-zA-Z0-9][_]{1}")
# >>> c.sub(".", module)
info_table = html.Div(
    [
        dt.DataTable(
            id="info-table",
            columns=[{"id": "module", "name": "module"},
                     {"id": "function", "name": "function"}],
            data=None,
            selected_rows=[0],
            sort_action="native",
            cell_selectable=False,
            row_selectable="multi",
            fixed_columns={"headers": True, "data": 0},
            style_table={
                "overflowY": "auto"
            }, css=[{"selector": ".row", "rule": "margin: 0"}]),
        html.Div(id="data-choosen", className="mini_container",
                 children=dcc.Markdown(id="data-choosen-txt"))
    ],
    style={"display": "flex", "flex-direction": "column",
           "justify-content": "start", "align-items": "flex-start"},
    className="pretty_container"
)

mode_selector = html.Div([
    html.P(
        "Selects mode:",
        className="control_label",
    ),
    dcc.RadioItems(
        id="timeline-mode",
        options=[
            {"label": "Mean", "value": "mean"},
            {"label": "Standard deviation", "value": "std"},
            {"label": "Significant bits", "value": "sig"}
        ],
        value="sig",

        className="dcc_control",
    )], className="mini_container")

xscale_selector = html.Div([
    html.P("X-scale:",
           className="control_label"),
    dcc.RadioItems(
        id="x-scale",
        options=[
            {"label": "linear", "value": "linear"},
            {"label": "log", "value": "log"}
        ],
        value="linear",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")

yscale_selector = html.Div([
    html.P("Y-scale:",
           className="control_label"),
    dcc.RadioItems(
        id="y-scale",
        options=[
            {"label": "linear", "value": "linear"},
            {"label": "log", "value": "log"},
        ],
        value="linear",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")

xformat_selector = html.Div([
    html.P("X-format:",
           className="control_label"),
    dcc.RadioItems(
        id="x-format",
        options=[
            {"label": "normal", "value": ""},
            {"label": "exponent", "value": "e"},
        ],
        value="",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")

yformat_selector = html.Div([
    html.P("Y-format:",
           className="control_label"),
    dcc.RadioItems(
        id="y-format",
        options=[
            {"label": "normal", "value": ""},
            {"label": "exponent", "value": "e"},
        ],
        value="",
        labelStyle={"display": "inline-block"},
        className="dcc_control",
    )], className="mini_container")

time_range_selector = html.Div([
    html.P("Filter time",
           className='control_label'),
    dcc.Input(id='time-start', placeholder='Start'),
    dcc.Input(id='time-end', placeholder='End')
])

timeline_hover_info = html.Div(
    dcc.Markdown(id="info-data-timeline-summary"),
    className="mini_container"
)

timeline_hover_heatmap = html.Div(
    dcc.Graph(id="info-data-timeline-heatmap"),
    className="pretty_container"
)


heatmap_colors_selector = html.Div([
    html.Div([
        html.Label(["Color map style",
                    dcc.Dropdown(
                        id='color-heatmap-style',
                        options=[
                            {"label": 'sequential', 'value': 'sequential'},
                            {'label': 'diverging', 'value': 'diverging'}
                        ]
                    )], className='mini_container'),
        html.Label(["Color map selection",
                    dcc.Dropdown(
                        id='color-heatmap',
                        options=[]
                    )], className='mini_container'),
        # html.Button('Animation', id='animate-heatmap', n_clicks=0)],
    ],
        className="mini_container",
        style={"display": "flex", "display-direction": "row", 'width': '100%'})
]
)

timeline_hover = html.Div(
    [
        timeline_hover_info,
        timeline_hover_heatmap,
        heatmap_colors_selector
    ],
    id="info-timeline",
    className="pretty_container",
    style={"display": "flex", "display-direction": "row"}
)

modal = html.Div(
    [
        dash_ace.DashAceEditor(id="source-modal-body-md",
                               value="..",
                               theme='github',
                               mode='python',
                               tabSize=2,
                               style={"marginBottom": 10,
                                      "width": "100%",
                                               "height": "100%",
                                               "overflowY": "scroll"}),


    ],
    id="source-file",
    className="mini_container",
    # className="row flex-display",
    # className="pretty_container ten columns",
    style={"display": "flex", "height": 400})

timeline_graph = html.Div([
    dcc.Graph(id="timeline",
              config={'responsive': False,
                      'autosizable': True,
                      'showLink': True}),
    html.Div(
        [
            html.Div(
                [
                    dcc.Link(id="source-link", href=""),
                    dcc.Markdown(id="source",
                                 style={"overflowY": "auto",
                                        "height": "200"}),
                ], className="mini_container",
                style={'width': "100%"}
            ),
            html.Div(
                [
                    daq.BooleanSwitch(label="Show source",
                                      id="source-button", on=False)
                ], className="mini_container",
                style={'width': "25%"}),
            html.Div(
                [
                    dcc.Input(id='lines-start', placeholder='Start'),
                    dcc.Input(id='lines-end', placeholder='End'),
                    dcc.Input(id='lines-file-selection',
                              placeholder='Filename'),
                    daq.BooleanSwitch(label="Fix source range",
                                      id='line-button', on=False),
                    html.Div(id='lines-slider-selection'),
                ], className="mini_container",
                style={'width': "100%", 'align-items': 'center', 'justify-content': 'center'})
        ], className="mini_container",
        style={"display": "flex", "flex-direction": "row"},
    ),
    timeline_hover,
])

info_ctx_debug = html.Div(
    [
        dcc.Textarea(id="debug-ctx",
                     style={"witdth": "100%", "height": 200}
                     )],
    className="mini_container")

header_title = html.Div(
    [
        html.Div(
            [
                html.H3(
                    "Pytracer Visualizer",
                    style={"margin-bottom": "0px"},
                ),
                html.H5(
                    "", style={"margin-top": "0px"}
                ),
            ]
        )
    ],
    className="eight column",
    id="title",
)

header_link = html.Div(
    [
        html.A(
            html.Button("Learn More", id="learn-more-button"),
            href="https://github.com/yohanchatelain",
        )
    ],
    className="one-third column",
    id="button",
)


header = html.Div(
    [
        header_title,
        header_link
    ],
    id="header",
    className="row flex-display",
    style={"margin-bottom": "25px"}
)

sidebar = info_table


def get_gantt(callgraph):
    gantt = pgc.get_gantt(callgraph)
    start_time = [pcc.convert_date_to_time(point['Start']) for point in gantt]
    end_time = [pcc.convert_date_to_time(point['Finish']) for point in gantt]
    if start_time == [] or end_time == []:
        return dcc.Graph(id='gantt', figure=None)
    max_time = int(max(max(start_time), max(end_time)))
    time = [t for t in range(max_time+1)]
    date = [pcc.convert_time_to_date(t) for t in time]
    fig = px.timeline(gantt, y="Task", x_start='Start', x_end='Finish')
    fig.update_xaxes(tickformat=f'%s', overwrite=True)
    fig.update_yaxes(tickwidth=1, ticklen=1)
    return dcc.Graph(id='gantt', figure=fig)


def get_rootpanel(args):
    return html.Div(
        [
            html.Div(
                [
                    mode_selector,
                    xscale_selector,
                    yscale_selector,
                    xformat_selector,
                    yformat_selector,
                    time_range_selector,
                ],
                className="pretty_container",
                style={"display": "flex",
                       "flex-direction": "row", "width": '90vh'},
                id="cross-filter-options"
            ),
            html.Div(
                [
                    get_gantt(args.callgraph),
                ],
                className="pretty_container",
                style={"display": "flex",
                       "flex-direction": "column", 'width': '90vh'}
            ),
            html.Div(
                [
                    timeline_graph,
                ],
                className="pretty_container",
                style={"display": "flex",
                       "flex-direction": "column", 'width': '90vh'}
            )
        ],
        id="mainContainer",
        style={"display": "flex", "flex-direction": "column",
               "justify-direction": "stretch",
               'width': '100vh'}
    )
