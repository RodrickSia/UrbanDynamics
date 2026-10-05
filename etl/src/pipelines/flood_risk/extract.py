from src.shared.data_io import data_dir, read_json
from src.shared.database import read_layer_document


def run(weather_input=None, history_input=None):
    directory = data_dir()
    try:
        floods = read_layer_document("flood_history")
    except FileNotFoundError:
        floods = read_json(directory / "layers" / "flood_history.geojson")
    return (
        floods,
        read_json(weather_input or directory / "inputs" / "rainwater_forecast.json"),
        read_json(history_input or directory / "inputs" / "rainwater_history.json"),
    )
