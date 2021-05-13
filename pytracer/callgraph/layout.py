import sys
import plotly.express as px
import dash_html_components as html
import dash_cytoscape as cyto
import dash_core_components as dcc
import dash_daq as daq
from pytracer.callgraph.layout_style import *

cyto.load_extra_layouts()


# Taken from https://github.com/plotly/dash-cytoscape/blob/master/demos/dash_reusable_components.py
def DropdownOptionsList(args):
    print(args)
    return [{'label': val[1], 'value': val[0]} for val in args.items()]


def NamedDropdown(name, **kwargs):
    return html.Div(
        style={'margin': '10px 0px'},
        children=[
            html.P(
                children=f'{name}:',
                style={'margin-left': '3px'}
            ),

            dcc.Dropdown(**kwargs)
        ]
    )


def NamedRadioItems(name, **kwargs):
    return html.Div(
        style={'padding': '20px 10px 25px 4px'},
        children=[
            html.P(children=f'{name}:'),
            dcc.RadioItems(**kwargs,
                           labelStyle={'display': 'inline-block'}
                           )
        ],
    )


g1 = cyto.Cytoscape(
    id='cytoscape',
    elements=[{'data': {'id': 'empty', 'label': 'empty'}}],
    layout={'name': 'klay'},
    boxSelectionEnabled=True,
    userPanningEnabled=True,
    style={
        'height': '95vh',
        'width': '100%'
    },
    stylesheet=[
        normal_node_style['style'],
        parent_node_style['style'],
        normal_edge_style['style'],
        factor_edge_style['style'],
        temporal_edge_style['style'],
        cycle_node_style['style'],
        root_node_style['style'],
        leaf_node_style['style'],
        isolate_node_style['style'],
        standard_node_style['style'],
        hidden_node_style['style']
    ])


def TopLevelGraph(elements):
    return cyto.Cytoscape(
        id='cytoscape-toplevel',
        elements=elements,
        layout={'name': 'circle'},
        stylesheet=[
            normal_node_style['style'],
            parent_node_style['style'],
            normal_edge_style['style'],
            factor_edge_style['style'],
            temporal_edge_style['style'],
            cycle_node_style['style'],
            root_node_style['style'],
            leaf_node_style['style'],
            isolate_node_style['style'],
            standard_node_style['style'],
            hidden_node_style['style']
        ])


def GanttGraph(elements):
    print(elements)
    return dcc.Graph(id='gantt', figure=px.timeline(elements, y="Task", x_start='Start', x_end='Finish'))


def RootsItems(options):
    return NamedRadioItems(name='Expand',
                           id='radio-expand',
                           options=DropdownOptionsList(options))


_layouts = {
    'random': 'random',
    'grid': 'grid',
    'circle': 'circle',
    'concentric': 'concentric',
    'breadthfirst': 'breadthfirst',
    'cose': 'cose',
    'cose-bilkent': 'cose-bilkent',
    'cola': 'cola',
    'spread': 'spread',
    'dagre': 'dagre',
    'klay': 'klay'
}


def LayoutItems():
    return NamedDropdown(
        name='Layout',
        id='dropdown-layout',
        options=DropdownOptionsList(_layouts),
        value='cose-bilkent',
        clearable=False
    )


def TapObject():
    return dcc.Tab(label='Tap Objects', children=[
        html.Div(style=styles['tab'], children=[
            html.P('Node Object JSON:'),
            html.Pre(
                id='tap-node-json-output',
                style=styles['json-output']
            ),
            html.P('Edge Object JSON:'),
            html.Pre(
                id='tap-edge-json-output',
                style=styles['json-output']
            )
        ])
    ])


def TapData():
    return dcc.Tab(label='Tap Data', children=[
        html.Div(style=styles['tab'], children=[
            html.P('Node Data JSON:'),
            html.Pre(
                id='tap-node-data-json-output',
                style=styles['json-output']
            ),
            html.P('Edge Data JSON:'),
            html.Pre(
                id='tap-edge-data-json-output',
                style=styles['json-output']
            )
        ])
    ])


def MouseoverData():
    return dcc.Tab(label='Mouseover Data', children=[
        html.Div(style=styles['tab'], children=[
            html.P('Node Data JSON:'),
            html.Pre(
                id='mouseover-node-data-json-output',
                style=styles['json-output']
            ),
            html.P('Edge Data JSON:'),
            html.Pre(
                id='mouseover-edge-data-json-output',
                style=styles['json-output']
            )
        ])
    ])


def SelectedData():
    return dcc.Tab(label='Selected Data', children=[
        html.Div(style=styles['tab'], children=[
            html.P('Node Data JSON:'),
            html.Pre(
                id='selected-node-data-json-output',
                style=styles['json-output']
            ),
            html.P('Edge Data JSON:'),
            html.Pre(
                id='selected-edge-data-json-output',
                style=styles['json-output']
            )
        ])
    ])


def ResetView():
    return daq.StopButton(
        id='reset-view-button',
        buttonText='Reset View',
        n_clicks=0
    )


def ControlPanel(options, gantt):
    return dcc.Tab(label='Control Panel', children=[
        LayoutItems(),
        ResetView(),
        TopLevelGraph(options),
        GanttGraph(gantt)
        # RootsItems(options),

    ])


def get_general_layout(options, gantt):
    return html.Div([
        html.Div(className='eight columns', children=[g1]),

        html.Div(className='four columns', children=[
            dcc.Tabs(id='tabs', children=[
                ControlPanel(options, gantt),
                TapObject(),
                TapData(),
                MouseoverData(),
                SelectedData()
            ]),

        ])
    ])


def init(**kwargs):
    roots = kwargs['roots']
    gantt = kwargs['gantt']
    return get_general_layout(roots, gantt)
