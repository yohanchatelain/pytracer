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
    dash.dependencies.Output("info-data-timeline-heatmap", "figure"),
    dash.dependencies.Output("info-timeline", "style"),
    [dash.dependencies.Input("timeline", "hoverData"),
     dash.dependencies.Input("timeline-mode", "value")])
def print_heatmap(hover_data, mode):
    b = time.perf_counter()
    figure = dict()
    display = {"display": "flex", "display-direction": "row"}
    # display = {"display": "none"}

    if hover_data:
        if "customdata" in hover_data["points"][0]:
            customdata = hover_data["points"][0]["customdata"]
            if "extra" in customdata:
                _ndarray = np.array(customdata["extra"])
                ndim = _ndarray.ndim

                if ndim == 1:
                    _ndarray = _ndarray.reshape(_ndarray.shape+(1,))
                _row, _col = _ndarray.shape
                _x = [i for i in range(_row)]
                _y = [i for i in range(_col)]
                if mode == "sig":
                    heatmap = go.Figure(data=go.Heatmap(x=_x,
                                                        y=_y,
                                                        z=_ndarray,
                                                        zmin=0,
                                                        zmax=64))
                else:
                    heatmap = go.Figure(data=go.Heatmap(x=_x,
                                                        y=_y,
                                                        z=_ndarray))

                figure = heatmap
                figure.update_layout(width=700, height=700)
                display = {"display": "flex", "display-direction": "row"}

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


@ app.callback(
    dash.dependencies.Output("source", "children"),
    dash.dependencies.Output("source-link", "href"),
    dash.dependencies.Output("source-link", "children"),
    [dash.dependencies.Input("timeline", "hoverData"),
     dash.dependencies.Input('source-file-path', 'value')])
# @cache.memoize(timeout=TIMEOUT)
def print_source(hover_data, source_path):
    b = time.perf_counter()

    line = ""
    source = ""
    description = ""

    if hover_data:
        customdata = hover_data["points"][0]["customdata"]
        [_source, _line, _lineno] = customdata["backtrace"]
        line = f"```py{os.linesep} {_line}{os.linesep}```"
        if os.path.isfile(_source):
            source = _source
        else:
            source = find_file_in_path(source_path, _source)
            source = source if source else _source
        description = f"{_source}:{_lineno}"

    e = time.perf_counter()
    print("print_source", e-b)
    return line, source, description


@app.callback(dash.dependencies.Output('lines-slider-selection', 'children'),
              dash.dependencies.Input('lines-start', 'value'),
              dash.dependencies.Input('lines-end', 'value'))
def print_line_selection(start, end):
    return f"Selected lines: {start}:{end}"


@ app.callback(
    # dash.dependencies.Output("source-modal-body-md", "children"),
    dash.dependencies.Output("source-file", "children"),
    [dash.dependencies.Input("source-button", "on"),
     dash.dependencies.Input("source-link", "href")])
# @cache.memoize(timeout=TIMEOUT)
def print_modal_source(on, href):
    b = time.perf_counter()
    source_code = "No source code found..."
    md = None
    if on:
        if href:
            if os.path.isfile(href):
                nl = os.linesep
                with open(href, "r") as fi:
                    source_code = "".join(fi.readlines())
            md = dash_ace.DashAceEditor(id="source-modal-body-md",
                                        value=source_code,
                                        theme='github',
                                        mode='python',
                                        tabSize=2,
                                        style={"marginBottom": 10,
                                               "width": "100%",
                                               "height": "100%",
                                               "overflowY": "scroll"})

    e = time.perf_counter()
    print("print_modal_source", e-b)
    return md


@ app.callback(
    dash.dependencies.Output("info-data-timeline-summary", "children"),
    dash.dependencies.Input("timeline", "hoverData"))
def print_datahover_summary(hover_data):
    b = time.perf_counter()
    text = ""
    if hover_data:
        if "customdata" in hover_data["points"][0]:

            customdata = hover_data["points"][0]["customdata"]
            if "extra" in customdata:

                _ndarray = np.array(customdata["extra"])
                ndim = _ndarray.ndim

                if ndim == 1:
                    (_size,) = _ndarray.shape
                    norm_fro = np.linalg.norm(_ndarray)
                    norm_inf = np.linalg.norm(_ndarray, ord=np.inf)
                    text = (f"shape={_size}{os.linesep}{os.linesep}"
                            f"Frobenius norm={norm_fro:.2}{os.linesep}{os.linesep}"
                            f"Inf norm={norm_inf:.2}{os.linesep}{os.linesep}")

                elif ndim == 2:
                    _row, _col = _ndarray.shape
                    norm_fro = np.linalg.norm(_ndarray)
                    norm_inf = np.linalg.norm(_ndarray, ord=np.inf)
                    cond = np.linalg.cond(_ndarray)
                    text = (f"shape={_row}x{_col}{os.linesep}{os.linesep}"
                            f"Frobenius norm={norm_fro:.2}{os.linesep}{os.linesep}"
                            f"Inf norm={norm_inf:.2}{os.linesep}{os.linesep}"
                            f"Cond={cond:.2e}{os.linesep}{os.linesep}")

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


@cache.memoize(timeout=TIMEOUT)
def get_scatter_timeline(module, function, label, backtrace, arg, mode, marker_symbol,
                         marker_color, customdata=None):
    b = time.perf_counter()

    b1 = time.perf_counter()

    def get_x(row):
        return row["label"] == bytes(label, "utf-8") and \
            row["name"] == arg and \
            row["BacktraceDescription"] == backtrace

    x = pgc.data.filter(module, function, get_x, "time")
    y = pgc.data.filter(module, function, get_x, mode)
    (filename, line, lineno, name) = backtrace

    e1 = time.perf_counter()
    print("pgc.data.filter x,y", e1-b1)

    b2 = time.perf_counter()

    backtracejoined = np.array(
        [filename.decode('utf-8'), line.decode('utf-8'), lineno])
    customdata = []
    if pgc.data.has_extra_value(module, function):
        _tmp = []
        extra_values = pgc.data.get_extra_value(
            module, function, label=label, arg=arg.decode("utf-8"), mode=mode)
        for _x in x:
            found = False
            for ev in extra_values:
                if ev.name.find(str(_x)):
                    found = True
                    _tmp.append(
                        {"backtrace": backtracejoined, "extra": np.array(ev)})
                    break
            if not found:
                _tmp.append({"backtrace": backtracejoined})
        customdata.extend(_tmp)
    else:
        customdata.extend([{"backtrace": backtracejoined}]*len(x))

    e2 = time.perf_counter()
    print("extra_value", e2-b2)

    b3 = time.perf_counter()
    scatter = go.Scattergl(name=f"{arg} - {lineno}",
                           legendgroup=f"group{backtrace}",
                           x=x,
                           y=y,
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
                label, backtraces_set, argsname, colors, marker, mode):
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
                                           colors[backtrace])

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
     ])
def update_timeline(selected_rows, data, mode, xscale, yscale,
                    xfmt, yfmt, line_on, curr_fig, lstart, lend, lfile):
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

    fig = go.Figure()
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
                    argsname=argsname, colors=colors, marker="triangle-up", mode=mode)

        names = pgc.data.filter(
            module, function, lambda row: row["label"] == b"outputs", "name")
        argsname = set(names)

        add_scatter(fig=fig,
                    module=module, function=function,
                    label="outputs", backtraces_set=backtraces_set,
                    argsname=argsname, colors=colors, marker="triangle-down", mode=mode)

    e = time.perf_counter()
    print("update_timeline", e-b)
    return fig
