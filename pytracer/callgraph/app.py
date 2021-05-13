
import dash

external_stylesheets = [
    "https://github.com/plotly/dash-app-stylesheets/blob/master/dash-oil-and-gas.css"]

app = dash.Dash(__name__,
                external_stylesheets=[external_stylesheets],
                meta_tags=[{"name": "viewport", "content": "width=device-width"}])

server = app.server
