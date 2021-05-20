import plotly.express as px
import sys
import astroid
import cProfile
from threading import TIMEOUT_MAX
import dash
from dash import dependencies
from pkg_resources import resource_string
import plotly.graph_objs as go
import os
import numpy as np
import plotly.colors as pcolors
import tables
import time
from flask_caching import Cache
import dash_ace
from pytracer.gui.app import app
import pytracer.gui.core as pgc
import dash_core_components as dcc
import dash_html_components as html

TIMEOUT = 60

cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache-directory'
})


@app.callback(
    dash.dependencies.Output("info-table", "data"),
    dash.dependencies.Input("output-clientsid", "loading_state"))
def init_info_table(loading_state):
    b = time.perf_counter()
    header = pgc.get_data().get_header()
    e = time.perf_counter()
    print("init_info_table", e-b)
    return header


@ app.callback(
    dash.dependencies.Output("data-choosen-txt", "children"),
    [dash.dependencies.Input("info-table", "selected_rows"),
     dash.dependencies.Input("info-table", "data")])
def update_table_active_cell(selected_rows, data):
    b = time.perf_counter()
    rows = pgc.get_active_row(selected_rows, data)
    rows_str = [
        f"module: {d['module']}, function: {d['function']}" for d in rows]
    msg = f"Selected rows:\n {os.linesep.join(rows_str)}"
    e = time.perf_counter()
    print("update_table_active_cell", e-b)
    return msg


@app.callback(
    dash.dependencies.Output('color-heatmap', 'options'),
    dash.dependencies.Input('color-heatmap-style', 'value'))
def fill_heatmap_color(color_style):
    if color_style is None:
        return []
    style = getattr(px.colors, color_style)
    available_colors = px.colors.named_colorscales()

    colors = []
    for attr in dir(style):
        if "_r" in attr:
            attr_lower = attr.replace('_r', '').lower()
        else:
            attr_lower = attr.lower()
        if attr_lower in available_colors:
            colors.append({'label': attr, 'value': attr})
    return colors


def str_to_utf8(string):
    return bytes(string, 'utf-8')


def utf8_to_str(utf8):
    return utf8.decode('utf-8')


def frame_args(duration):
    return {
        "frame": {"duration": duration},
        "mode": "immediate",
        "fromcurrent": True,
        "transition": {"duration": duration, "easing": "linear"},
    }


@app.callback(
    dash.dependencies.Output("info-data-timeline-heatmap", "figure"),
    dash.dependencies.Output("info-timeline", "style"),
    [dash.dependencies.Input("timeline", "hoverData"),
     dash.dependencies.Input("timeline-mode", "value"),
     dash.dependencies.Input('color-heatmap', 'value'),
     dash.dependencies.Input('z-scale', 'value'),
     dash.dependencies.State('info-data-timeline-heatmap', 'figure'),
     dash.dependencies.State('lines-start', 'value'),
     dash.dependencies.State('lines-end', 'value'),
     ])
def print_heatmap(hover_data, mode, color, zscale, fig, lstart, lend):
    b = time.perf_counter()
    figure = dict()
    display = {"display": "flex", "display-direction": "row"}

    ctx = dash.callback_context

    extra_value = None
    if hover_data:
        x = hover_data['points'][0]['x']
        info = hover_data['points'][0]['customdata']

        try:
            extra_value = pgc.data.get_extra_value(info['module'],
                                                   info['function'],
                                                   info['label'],
                                                   info['arg'],
                                                   x,
                                                   mode)

        except KeyError:
            extra_value = None

    if extra_value:
        _ndarray = extra_value.read()
        ndim = _ndarray.ndim

        if ndim == 1:
            _ndarray = _ndarray.reshape(_ndarray.shape+(1,))
        if ndim == 3:
            _row = _ndarray.shape[0]
            _col = _ndarray.shape[1] * _ndarray.shape[2]
            _ndarray = _ndarray.reshape((_row, _col))
        if ndim > 3:
            _row = _ndarray.shape[0]
            _col = np.prod(_ndarray.shape[1:])
            _ndarray = _ndarray.reshape((_row, _col))

        if zscale == 'log':
            _ndarray = np.log(np.abs(_ndarray))

        _row, _col = _ndarray.shape
        _x = [i for i in range(_row)]
        _y = [i for i in range(_col)]
        if mode == "sig":
            heatmap = go.Figure(data=go.Heatmap(x=_x,
                                                y=_y,
                                                z=_ndarray,
                                                zmin=0,
                                                zmax=64,
                                                coloraxis='coloraxis'))
        else:
            heatmap = go.Figure(data=go.Heatmap(x=_x,
                                                y=_y,
                                                z=_ndarray,
                                                coloraxis='coloraxis'))

        figure = heatmap
        figure.update_layout(width=700, height=700)

        if color:
            colorscale = dict(colorscale=color)
            if mode == "sig":
                colorscale['cmin'] = 0
                colorscale['cmax'] = 53
            figure.update_layout(coloraxis=colorscale)

    if ctx.triggered:
        if ctx.triggered[0]['prop_id'] == 'color-heatmap.value':
            colorscale = dict(colorscale=color)
            if mode == "sig":
                colorscale['cmin'] = 0
                colorscale['cmax'] = 53
            fig = go.Figure(fig)
            fig.update_layout(coloraxis=colorscale)
            figure = fig

    e = time.perf_counter()
    print("print_heatmap", e-b)
    return (figure, display)


path_cache = dict()


def find_file_in_path(path, filename):
    if path is None:
        return []

    if (key := (path, filename)) in path_cache:
        return path_cache[key]

    subpath = filename.rpartition('site-packages')[-1]
    prefix, name = os.path.split(subpath)

    file_found = None
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                if prefix in root and name == file:
                    file_found = f"{root}{os.sep}{file}"
    if file_found:
        path_cache[(path, filename)] = file_found
    return file_found


__source_line_cache = dict()


def get_full_source_line(path, line):
    if (key := (path, line)) in __source_line_cache:
        return __source_line_cache[key]

    fi = open(path)
    source = fi.read()
    m = astroid.parse(source)
    for call in m.nodes_of_class(astroid.Call):
        if call.lineno == int(line):
            source = call.statement()
            key = (path, line)
            __source_line_cache[key] = source
            return source
    return None


@ app.callback(
    dash.dependencies.Output("source", "children"),
    dash.dependencies.Output("source-link", "href"),
    dash.dependencies.Output("source-link", "children"),
    [dash.dependencies.Input("timeline", "hoverData")])
# @cache.memoize(timeout=TIMEOUT)
def print_source(hover_data):
    b = time.perf_counter()

    line = ""
    source = ""
    description = ""

    if hover_data:
        customdata = hover_data["points"][0]["customdata"]
        source = customdata["filename"]
        _lineno = customdata['lineno']
        path = f"{pgc.data.source_path}{os.sep}{source}"
        if os.path.isfile(path):
            line = get_full_source_line(path, _lineno)
            line = f'```py{os.linesep} {line.as_string()}{os.linesep}```'
        else:
            raise FileNotFoundError
        description = f"{source}:{_lineno}"

    e = time.perf_counter()
    print("print_source", e-b)
    return line, source, description


@ app.callback(dash.dependencies.Output('lines-slider-selection', 'children'),
               dash.dependencies.Input('lines-start', 'value'),
               dash.dependencies.Input('lines-end', 'value'))
def print_line_selection(start, end):
    return f"Selected lines: {start}:{end}"


@ app.callback(
    # dash.dependencies.Output("source-modal-body-md", "children"),
    dash.dependencies.Output("source-file", "children"),
    [dash.dependencies.Input("source-button", "on"),
     dash.dependencies.Input("source-link", "href")],
    dash.dependencies.State('source-link', "children"))
# @cache.memoize(timeout=TIMEOUT)
def print_modal_source(on, href, href_description):
    b = time.perf_counter()
    source_code = "No source code found..."
    md = None
    if on:
        if href:
            path = f"{pgc.data.source_path}{os.sep}{href}"
            lineno = href_description.split(':')[-1]
            line = get_full_source_line(path, lineno)
            line_start = line.fromlineno
            line_end = line.tolineno
            print(f"Line {line_start}:{line_end}")
            if os.path.isfile(path):
                fi = open(path)
                source_code = fi.read()
            md = dash_ace.DashAceEditor(id="source-modal-body-md",
                                        value=source_code,
                                        theme='github',
                                        mode='python',
                                        tabSize=2,
                                        focus=True,
                                        enableSnippets=True,
                                        style={"marginBottom": 10,
                                               "width": "100%",
                                               "height": "100%",
                                               "overflowY": "scroll"},
                                        markers=[{'startRow': line_start,
                                                  'startCol': 0,
                                                  'endRow': line_end,
                                                  'endCol': 20,
                                                  'className': 'error-marker',
                                                  'type': 'background'}],
                                        annotations=[{'row': line_start-1,
                                                      'type': 'error', 'text': 'Current call'}])

    e = time.perf_counter()
    print("print_modal_source", e-b)
    return md


@ app.callback(
    dash.dependencies.Output("info-data-timeline-summary", "children"),
    [dash.dependencies.Input("timeline", "hoverData"),
     dash.dependencies.Input("info-data-timeline-heatmap", "figure")],
    dash.dependencies.State('timeline-mode', 'value'))
def print_datahover_summary(hover_data, fig, mode):
    b = time.perf_counter()
    text = ""
    if hover_data:
        print(f'hover_data {hover_data}')
        x = hover_data['points'][0]['x']
        info = hover_data['points'][0]['customdata']
        extra_value = None
        try:
            extra_value = pgc.data.get_extra_value(info['module'],
                                                   info['function'],
                                                   info['label'],
                                                   info['arg'],
                                                   x,
                                                   mode)
        except KeyError:
            extra_value = None

        if extra_value:
            _ndarray = extra_value.read()
            ndim = _ndarray.ndim

            if ndim == 1:
                (_size,) = _ndarray.shape
                norm_fro = np.linalg.norm(_ndarray)
                norm_inf = np.linalg.norm(_ndarray, ord=np.inf)
                cond = 1/norm_fro
                text = (f"Function={info['function']}{os.linesep*2}"
                        f"Arg={info['arg']}{os.linesep*2}"
                        f"shape={_size}{os.linesep}{os.linesep}"
                        f"Frobenius norm={norm_fro:.2}{os.linesep}{os.linesep}"
                        f"Inf norm={norm_inf:.2}{os.linesep}{os.linesep}"
                        f"Cond={cond:.2e}{os.linesep}{os.linesep}")

            elif ndim == 2:
                _row, _col = _ndarray.shape
                norm_fro = np.linalg.norm(_ndarray)
                norm_inf = np.linalg.norm(_ndarray, ord=np.inf)
                norm_2 = np.linalg.norm(_ndarray, ord=2)
                cond = np.linalg.cond(_ndarray)
                text = (f"Function={info['function']}{os.linesep*2}"
                        f"Arg={info['arg']}{os.linesep*2}",
                        f"shape={_row}x{_col}{os.linesep}{os.linesep}"
                        f"Frobenius norm={norm_fro:.2}{os.linesep}{os.linesep}"
                        f"Inf norm={norm_inf:.2}{os.linesep}{os.linesep}"
                        f"2-norm={norm_2:.2}{os.linesep}{os.linesep}"
                        f"Cond={cond:.2e}{os.linesep}{os.linesep}")

            elif ndim > 2:
                shape = "x".join(map(str, _ndarray.shape))
                norm_fro = np.linalg.norm(_ndarray)
                text = (f"Function={info['function']}{os.linesep*2}"
                        f"Arg={info['arg']}{os.linesep*2}"
                        f"shape={shape}{os.linesep}{os.linesep}"
                        f"Frobenius norm={norm_fro:.2}{os.linesep}{os.linesep}")

    e = time.perf_counter()
    print("print_datahover_summary", e-b)
    return text


@ app.callback(
    dash.dependencies.Output("source-file", "style"),
    dash.dependencies.Input("source-button", "on"))
def open_modal_source(on):
    b = time.perf_counter()
    style_off = {"display": "none"}
    style_on = {"display": "block", "width": "100%", "height": 300}
    e = time.perf_counter()
    print("open_modal_source", e-b)
    return style_on if on else style_off


# @cache.memoize(timeout=TIMEOUT)
def get_scatter_timeline(module, function, label, backtrace, arg, mode, marker_symbol,
                         marker_color, customdata=None, time_start=-1, time_end=sys.maxsize):
    b = time.perf_counter()

    b1 = time.perf_counter()

    def get_x(row):
        return row["label"] == bytes(label, "utf-8") and \
            row["name"] == arg and \
            row["BacktraceDescription"] == backtrace and \
            row['time'] >= time_start and \
            row['time'] <= time_end

    x = pgc.data.filter(module, function, get_x, "time")
    y = pgc.data.filter(module, function, get_x, mode)
    (filename, line, lineno, name) = backtrace

    e1 = time.perf_counter()
    print("pgc.data.filter x,y", e1-b1)

    b2 = time.perf_counter()

    info = {'module': module,
            'function': function,
            'label': label,
            'arg': arg.decode('utf-8'),
            'filename': filename.decode('utf-8'),
            'lineno': lineno,
            'name': name.decode('utf-8')}

    customdata = list()
    hovertext = list()
    for i in x:
        info['time'] = i
        customdata.append(info)
        hovertext.append(f"{function}{os.linesep}{arg.decode('utf-8')}")

    e2 = time.perf_counter()
    print("extra_value", e2-b2)

    b3 = time.perf_counter()
    scatter = go.Scattergl(name=f"{function} - {arg.decode('utf-8')} - {lineno}",
                           #    legendgroup=f"group{backtrace}",
                           x=x,
                           y=y,
                           hovertemplate='<b>X</b>: %{x}' +
                           '<br><b>Y</b>: %{y:.7e}<br>' +
                           '<b>%{text}</b>',
                           text=hovertext,
                           customdata=customdata,
                           mode="markers",
                           marker_symbol=marker_symbol,
                           marker_color=marker_color)
    e3 = time.perf_counter()
    print("scattergl", b3-e3)

    e = time.perf_counter()
    print("get_scatter_timeline", e-b)
    return scatter


def add_scatter(fig, module, function,
                label, backtraces_set,
                argsname, colors, marker, mode,
                time_start=0, time_end=sys.maxsize):
    b = time.perf_counter()

    for backtrace in backtraces_set:
        for arg in argsname:
            # ori_arg = find_calling_name(backtrace, arg)
            scatter = get_scatter_timeline(module,
                                           function,
                                           label,
                                           backtrace,
                                           arg,
                                           mode,
                                           marker,
                                           colors[backtrace],
                                           time_start=time_start,
                                           time_end=time_end)

            if scatter:
                fig.add_trace(scatter)

    e = time.perf_counter()
    print("add_scatter", e-b)


def get_name(astname):
    if isinstance(astname, astroid.Attribute):
        name = get_name(astname.expr)
        attr = astname.attr
        return f"{name}.{attr}"
    elif isinstance(astname, astroid.Name):
        name = astname.Name
        return f"{name}"
    elif isinstance(astname, astroid.Const):
        name = astname.value
        return f"{name}"
    else:
        raise TypeError


def get_first_call_from_line(lfile, lstart):
    src = None
    with open(lfile) as fi:
        src = "\n".join([_ for _ in fi])
    m = astroid.parse(src)
    calls = m.nodes_of_class(astroid.Call)
    calls_list = list()
    for call in calls:
        if call.lineno == lstart:
            calls_list.append(get_name(call.func))
    return calls_list


@ app.callback(
    dash.dependencies.Output("timeline", "figure"),
    [dash.dependencies.Input("info-table", "selected_rows"),
     dash.dependencies.Input("info-table", "data"),
     dash.dependencies.Input("timeline-mode", "value"),
     dash.dependencies.Input("x-scale", "value"),
     dash.dependencies.Input("y-scale", "value"),
     dash.dependencies.Input("x-format", "value"),
     dash.dependencies.Input("y-format", "value"),
     dash.dependencies.Input("line-button", "on"),
     dash.dependencies.State("timeline", "figure"),
     dash.dependencies.State("lines-start", "value"),
     dash.dependencies.State("lines-end", "value"),
     dash.dependencies.State("lines-file-selection", "value"),
     dash.dependencies.State("time-start", "value"),
     dash.dependencies.State("time-end", "value")
     ])
def update_timeline(selected_rows, data, mode, xscale, yscale,
                    xfmt, yfmt, line_on, curr_fig, lstart, lend, lfile,
                    time_start, time_end):
    ctx = dash.callback_context

    b = time.perf_counter()
    if ctx.triggered:
        print(ctx.triggered)
        trigger = ctx.triggered[0]['prop_id']
        if trigger in ("x-scale.value", 'y-scale.value', 'x-format.value', 'y-format.value'):
            value = ctx.triggered[0]['value']
            fig = go.Figure(curr_fig)
            if trigger == 'x-scale.value':
                fig.update_xaxes(type=value)
            elif trigger == 'x-format.value':
                fig.update_xaxes(tickformat=value)
            elif trigger == 'y-scale.value':
                fig.update_yaxes(type=value)
            elif trigger == 'y-format.value':
                fig.update_yaxes(tickformat=value)
            print("Return fig")
            return fig

    fig = go.Figure(layout={'height': 800})
    ylabel = pgc.get_ylabel(mode)
    fig.update_xaxes(title_text="Invocation", type=xscale)
    fig.update_yaxes(title_text=ylabel,
                     rangemode="tozero", type=yscale)

    module_and_function = [data[selected_row]
                           for selected_row in selected_rows]

    if line_on:
        if os.path.isfile(lfile):
            calls = get_first_call_from_line(lfile, lstart)
            pgc.data.get_first_call_from_line(lstart)
        else:
            print(f"File {lfile} does not exit")

    time_start = -1 if time_start is None else int(time_start)
    time_end = sys.maxsize if time_end is None else int(time_end)

    for mf in module_and_function:
        module = mf["module"]
        function = mf["function"]

        backtraces = pgc.data.filter(
            module, function, lambda row: row["label"] == b"inputs", "BacktraceDescription")
        backtraces_set = set(backtraces)
        colors = {bt: pcolors.qualitative.Alphabet[i]
                  for i, bt in enumerate(backtraces_set)}

        names = pgc.data.filter(
            module, function, lambda row: row["label"] == b"inputs", "name")
        argsname = set(names)

        add_scatter(fig=fig,
                    module=module, function=function,
                    label="inputs", backtraces_set=backtraces_set,
                    argsname=argsname, colors=colors, marker="triangle-up", mode=mode,
                    time_start=time_start, time_end=time_end)

        names = pgc.data.filter(
            module, function, lambda row: row["label"] == b"outputs", "name")
        argsname = set(names)

        add_scatter(fig=fig,
                    module=module, function=function,
                    label="outputs", backtraces_set=backtraces_set,
                    argsname=argsname, colors=colors, marker="triangle-down", mode=mode,
                    time_start=time_start, time_end=time_end)

    e = time.perf_counter()
    print("update_timeline", e-b)
    return fig
