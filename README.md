# Pytracer

Pytracer is a python tracer designed to assess
the numerical quality of python codes.
Pytracer automatically instruments python modules
to trace the inputs and outputs of targeted modules' functions.
Generated traces are then aggregated and can be visualized
through a visualizer based on dash/plotly library.

# Usage

Pytracer is divided in three steps: trace, parse and visualize.

```bash
usage: pytracer [-h] [--clean] {trace,parse,visualize} ...

Pytracer

optional arguments:
  -h, --help            show this help message and exit
  --clean               Clean pytracer cache path

pytracer modules:
  {trace,parse,visualize}
                        pytracer modules
    trace               trace functions
    parse               parse traces
    visualize           visualize traces
```

The trace module takes as inputs an python application to run
and a list of modules to trace. The application is passed
through the `--module` option while the list of modules to trace
is passed through a configuration file. Once the modules are wrapped,
the trace module execute the application used with the `--module` option
as a script. The execution of the application will generate
a pickle file that contains all inputs/outputs encountered, called a trace.
Pytracer is designed to detect numerical instabilities and so
to work under stochastic arithmetic environment (see fuzzy).
The different executions of the targeted application under this
environment should result in floating-point values that differ from each
other. The parse module is attempted to gather these traces
and to compute statistics on the observed differences.
The parse module convert a set of traces into a hfd5 file used
for the visualization. Then the visualize module opens a dash server
to visualize the traces on a browser and to interact with them.

## Trace module

The trace module instruments modules in `config.modules_to_load`
and execute the `module` application.

```bash
usage: pytracer trace [-h] --module MODULE [--dry-run]

optional arguments:
  -h, --help       show this help message and exit
  --module MODULE  path of the module to trace
  --dry-run        Run the module wihtout tracing it
```
## Parse module

The parse module aggregates traces and produce a hdf5 file.

```bash
usage: pytracer parse [-h] [--filename FILENAME | --directory DIRECTORY] [--format {text,json,pickle}] [--timer]

optional arguments:
  -h, --help            show this help message and exit
  --filename FILENAME   only parse <filename>
  --directory DIRECTORY
                        parse all files in <directory>and merge them
  --format {text,json,pickle}
                        format of traces (auto-detected by default)
  --timer               Display timing for the parsing
```

## Visualize module

```bash
usage: pytracer visualize [-h] [--directory DIRECTORY] [--debug]

optional arguments:
  -h, --help            show this help message and exit
  --directory DIRECTORY
                        directory with traces
  --debug               rue dash server in debug mode
```

This command produces the following output:

```bash
Dash is running on http://127.0.0.1:8050/

 * Serving Flask app "pytracer.gui.app" (lazy loading)
 * Environment: production
   WARNING: This is a development server. Do not use it in a production deployment.
   Use a production WSGI server instead.
 * Debug mode: off
 * Running on http://127.0.0.1:8050/ (Press CTRL+C to quit)
```

You must open the address in a browser to see the trace.

## Config file

The configuration file is a `json` file containing several entries:

- `module_to_load`: String list. List of the modules to trace
- `include_file`: String list. List of the inclusion files. An inclusion file
restrict the function to trace for a given module.
- `exlude_file`: String list. List of the inclusion files. An inclusion file
list the function to do not trace for a given module.
- `filter_alias`: Boolean. Tells if alias functions must be traced.
- `logger`: Suboption for the logger.
    - `format`: {`print`,`logger`}. Which logger format used.
    - `output`: String. File where storing the log outputs.
    - `color`: Boolean. Enable colors.
    - `level`: {`debug`,`info`,`warning`}. Minimum level of information.
- `io`: Suboption for the trace.
    - `type`: {`pickle`}. Specify the format of the trace.
    - `backtrace`: Boolean. Enable backtracing.
    - `cache`: Suboption for the trace directory:
        - `root`: String. Name of the directory to store traces
- `numpy`: Suboption relative to numpy module
    - `ufunc`: Boolean. Enable tracing `ufunc` functions.