import json
import plotly.express as px
import astroid
import dash
import plotly.graph_objs as go
import os
import numpy as np
import plotly.colors as pcolors
import time
from flask_caching import Cache
import dash_ace
from pytracer.gui.app import app
import pytracer.gui.core as pgc
import threading
import random

lock = threading.Lock()

TIMEOUT = 60

cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',
    'CACHE_DIR': 'cache-directory'
})


@app.callback(
    dash.dependencies.Output("info-table", "data"),
    dash.dependencies.Input("output-clientsid", "loading_state"))
def init_info_table(loading_state):
    header = pgc.get_data().get_header()
    return header


@ app.callback(
    dash.dependencies.Output("data-choosen-txt", "children"),
    [dash.dependencies.Input("info-table", "selected_rows"),
     dash.dependencies.Input("info-table", "data")])
# @cache.memoize(timeout=TIMEOUT)
def update_table_active_cell(selected_rows, data):
    rows = pgc.get_active_row(selected_rows, data)
    rows_str = [
        f"module: {d['module']}, function: {d['function']}" for d in rows]
    msg = f"Selected rows:\n {os.linesep.join(rows_str)}"
    return msg


@app.callback(
    dash.dependencies.Output('color-heatmap', 'options'),
    dash.dependencies.Input('color-heatmap-style', 'value'),
    prevent_initial_call=True)
# @cache.memoize(timeout=TIMEOUT)
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

# @cache.memoize(timeout=TIMEOUT)


def str_to_utf8(string):
    return bytes(string, 'utf-8')

# @cache.memoize(timeout=TIMEOUT)


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
     ],
    prevent_initial_call=True)
def print_heatmap(hover_data, mode, color, zscale, fig):
    figure = {}
    display = {"display": "flex", "display-direction": "row"}

    ctx = dash.callback_context

    extra_value = None
    if hover_data:
        x = hover_data['points'][0]['x']
        info = hover_data['points'][0]['customdata']

        try:
            with lock:
                extra_value = pgc.data.get_extra_value(info['module'],
                                                       info['function'],
                                                       info['label'],
                                                       info['arg'],
                                                       x,
                                                       mode)

        except KeyError:
            extra_value = None

    if extra_value:
        with lock:
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
        _x = list(range(_row))
        _y = list(range(_col))
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

    return (figure, display)


path_cache = {}


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


__source_line_cache = {}


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
    [dash.dependencies.Input("timeline", "hoverData")],
    prevent_initial_call=True)
# @cache.memoize(timeout=TIMEOUT)
def print_source(hover_data):

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

    return line, source, description


@ app.callback(
    # dash.dependencies.Output("source-modal-body-md", "children"),
    dash.dependencies.Output("source-file", "children"),
    [dash.dependencies.Input("source-button", "on"),
     dash.dependencies.Input("source-link", "href")],
    dash.dependencies.State('source-link', "children"),
    prevent_initial_call=True)
# @cache.memoize(timeout=TIMEOUT)
def print_modal_source(on, href, href_description):
    source_code = "No source code found..."
    md = None
    if on:
        if href:
            path = f"{pgc.data.source_path}{os.sep}{href}"
            lineno = href_description.split(':')[-1]
            line = get_full_source_line(path, lineno)
            line_start = line.fromlineno
            line_end = line.tolineno
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

    return md


@ app.callback(
    dash.dependencies.Output("info-data-timeline-summary", "children"),
    [dash.dependencies.Input("timeline", "hoverData"),
     dash.dependencies.Input("info-data-timeline-heatmap", "figure")],
    dash.dependencies.State('timeline-mode', 'value'),
    prevent_initial_call=True)
def print_datahover_summary(hover_data, fig, mode):
    text = ""
    if hover_data:
        x = hover_data['points'][0]['x']
        info = hover_data['points'][0]['customdata']
        extra_value = None
        try:
            with lock:
                extra_value = pgc.data.get_extra_value(info['module'],
                                                       info['function'],
                                                       info['label'],
                                                       info['arg'],
                                                       x,
                                                       mode)
        except KeyError:
            extra_value = None

        if extra_value:
            with lock:
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

    return text


@ app.callback(
    dash.dependencies.Output("source-file", "style"),
    dash.dependencies.Input("source-button", "on"))
def open_modal_source(on):
    style_off = {"display": "none"}
    style_on = {"display": "block", "width": "100%", "height": 300}
    return style_on if on else style_off


# @cache.memoize(timeout=TIMEOUT)
def get_scatter_timeline(module, function, label, backtrace, arg, mode, marker_symbol,
                         marker_color, customdata=None):

    def get_x(values, col, *argv):
        arg = argv[0]
        label = argv[1]
        b_label = bytes(label, "utf-8")
        with lock:
            return [x[col] for x in values.where(
                '((name == arg) & (label == b_label))')
                if x["BacktraceDescription"] == backtrace
            ]

    x = pgc.data.filter(module, function, get_x, "time", arg, label)
    y = pgc.data.filter(module, function, get_x, mode, arg, label)
    (filename, line, lineno, name) = backtrace

    info = {'module': module,
            'function': function,
            'label': label,
            'arg': arg.decode('utf-8'),
            'filename': filename.decode('utf-8'),
            'lineno': lineno,
            'name': name.decode('utf-8')}

    customdata = []
    hovertext = []
    customdata_append = customdata.append
    hovertext_append = hovertext.append
    for i in x:
        info['time'] = i
        customdata_append(info)
        hovertext_append(f"{function}{os.linesep}{arg.decode('utf-8')}")

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
                           marker_color=marker_color,
                           meta={'module': module, 'function': function})
    return scatter

# @cache.memoize(timeout=TIMEOUT)


def add_scatter(fig, module, function,
                label, backtraces_set,
                argsname, colors, marker, mode):

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

            fig.add_trace(scatter)

# @cache.memoize(timeout=TIMEOUT)


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

# @cache.memoize(timeout=TIMEOUT)


def get_first_call_from_line(lfile, lstart):
    src = None
    with open(lfile) as fi:
        src = "\n".join([_ for _ in fi])
    m = astroid.parse(src)
    calls = m.nodes_of_class(astroid.Call)
    calls_list = []
    for call in calls:
        if call.lineno == lstart:
            calls_list.append(get_name(call.func))
    return calls_list


_colors_map = dict()


def get_colors(module, function):
    if (key := (module, function)) in _colors_map:
        return _colors_map[key]

    def get_x_in(values, col):
        b_inputs = b"inputs"
        with lock:
            return [x[col] for x in values.where('((label == b_inputs))')]

    def get_x_out(values, col):
        b_outputs = b"outputs"
        with lock:
            return [x[col] for x in values.where('((label == b_outputs))')]

    backtraces_in = pgc.data.filter(
        module, function, get_x_in, "BacktraceDescription")

    backtraces_out = pgc.data.filter(
        module, function, get_x_out, "BacktraceDescription")

    backtraces_set = set.union(set(backtraces_in), set(backtraces_out))

    _colors = pcolors.qualitative.Alphabet * 10
    random.shuffle(_colors)
    colors = {bt: _colors[i]
              for i, bt in enumerate(backtraces_set)}

    key = (module, function)
    value = (colors, backtraces_set)
    _colors_map[key] = value
    return value


def remove_scatter(figure, module, function):
    meta_to_remove = {'module': module, "function": function}
    for data in figure['data']:
        if data['meta'] == meta_to_remove:
            data['visible'] = False


@app.callback(
    dash.dependencies.Output("download-timeline", "data"),
    dash.dependencies.Input("dump-timeline", "n_clicks"),
    dash.dependencies.State("timeline", "figure"),
    prevent_initial_call=True
)
def dump_timeline(n_clicks, figure):
    data = json.dumps(figure, ensure_ascii=False, indent=2)
    return dict(content=data, filename='timeline.json')


@app.callback(
    dash.dependencies.Output("current-selected-rows", "data"),
    dash.dependencies.Output("previous-selected-rows", "data"),
    dash.dependencies.Input("info-table", "selected_rows"),
    dash.dependencies.State("current-selected-rows", "data")
)
def update_selected_rows(selected_rows, current_selection):
    return (selected_rows, current_selection)


@app.callback(
    dash.dependencies.Output("timeline", "figure"),
    [dash.dependencies.Input("current-selected-rows", "data"),
     dash.dependencies.Input("info-table", "data"),
     dash.dependencies.Input("timeline-mode", "value"),
     dash.dependencies.Input("x-scale", "value"),
     dash.dependencies.Input("y-scale", "value"),
     dash.dependencies.Input("x-format", "value"),
     dash.dependencies.Input("y-format", "value"),
     dash.dependencies.State("timeline", "figure"),
     dash.dependencies.State("previous-selected-rows", "data"),
     ])
def update_timeline(selected_rows, data, mode, xscale, yscale,
                    xfmt, yfmt, curr_fig, prev_selected_rows):
    ctx = dash.callback_context

    b = time.perf_counter()
    if ctx.triggered:
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
            return fig

    new_fig = go.Figure(layout={'height': 800})

    if curr_fig is None:
        fig = new_fig
    else:
        fig = go.Figure(curr_fig)

    if selected_rows == []:
        return new_fig
    else:
        rows_to_add = set.difference(
            set(selected_rows), set(prev_selected_rows))
        rows_to_remove = set.difference(
            set(prev_selected_rows), set(selected_rows))

    ylabel = pgc.get_ylabel(mode)
    fig.update_xaxes(title_text="Invocation", type=xscale)
    fig.update_yaxes(title_text=ylabel,
                     rangemode="tozero", type=yscale)

    module_and_function_to_add = [data[x] for x in rows_to_add]
    module_and_function_to_remove = [data[x] for x in rows_to_remove]

    # @cache.memoize(timeout=TIMEOUT)

    def get_x_in(values, col):
        b_inputs = b"inputs"
        with lock:
            return [x[col] for x in values.where('((label == b_inputs))')]

    # @cache.memoize(timeout=TIMEOUT)
    def get_x_out(values, col, *argv):
        b_outputs = b"outputs"
        with lock:
            return [x[col] for x in values.where('((label == b_outputs))')]

    for mf in module_and_function_to_add:
        module = mf["module"]
        function = mf["function"]

        colors, backtraces_set = get_colors(module, function)

        names = pgc.data.filter(
            module, function, get_x_in, "name")
        argsname = set(names)

        add_scatter(fig=fig,
                    module=module, function=function,
                    label="inputs", backtraces_set=backtraces_set,
                    argsname=argsname, colors=colors, marker="triangle-up", mode=mode)

        names = pgc.data.filter(
            module, function, get_x_out, "name")
        argsname = set(names)

        add_scatter(fig=fig,
                    module=module, function=function,
                    label="outputs", backtraces_set=backtraces_set,
                    argsname=argsname, colors=colors, marker="triangle-down", mode=mode)

    for mf in module_and_function_to_remove:
        module = mf["module"]
        function = mf["function"]
        remove_scatter(figure=fig, module=module, function=function)

    e = time.perf_counter()
    print("update_timeline", e-b)
    # print(fig.data)
    return fig


@app.callback(
    dash.dependencies.Output("histo_bin_selected", "children"),
    [dash.dependencies.Input("histo_bin_selector", "value")]
)
def update_histo_bin_selected(nb_bins):
    return f"Nb bins: {nb_bins}"


@app.callback(
    dash.dependencies.Output("histo_heatmap", "figure"),
    [dash.dependencies.Input("info-data-timeline-heatmap", "figure"),
     dash.dependencies.Input("histo_bin_selector", "value"),
     dash.dependencies.Input("histo_normalization", "value")],
    dash.dependencies.State("timeline-mode", "value"))
def update_histo(heatmap, nbins, normalization, mode):
    if heatmap == {} or heatmap is None:
        return {}
    x = np.ravel(heatmap['data'][0]['z'])
    fig = get_histo(x, nbins, normalization)

    mode_str = {"sig": "Significant digits",
                "mean": "Mean", "std": "Standard deviation"}
    fig.update_xaxes({"title": mode_str[mode]})
    fig.update_yaxes({"title": normalization if normalization else "count"})
    return fig


def get_histo(x, nbins, normalization):
    return go.Figure(data=go.Histogram(x=x, nbinsx=nbins, histnorm=normalization))
