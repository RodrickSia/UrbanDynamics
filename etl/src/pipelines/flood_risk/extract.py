from src.shared.data_io import data_dir, read_json
from src.shared.database import read_layer_document


def run(weather_input=None, history_input=None):
    directory = data_dir()
    from src.pipelines.rainwater.load import input_pair
    if weather_input or history_input:
        forecast = read_json(weather_input or directory/'inputs/rainwater_forecast.json')
        history = read_json(history_input or directory/'inputs/rainwater_history.json')
    else:
        forecast,history = input_pair(directory)
    try:
        floods = read_layer_document("flood_history")
    except FileNotFoundError:
        floods = read_json(directory / "layers" / "flood_history.geojson")
    return floods, forecast, history
