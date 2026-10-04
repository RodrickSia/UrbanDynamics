from src.shared.data_io import data_dir, read_json

def run(weather_input=None, history_input=None):
    directory = data_dir()
    return (read_json(directory / "layers" / "flood_history.geojson"),
            read_json(weather_input or directory / "inputs" / "rainwater_forecast.json"),
            read_json(history_input or directory / "inputs" / "rainwater_history.json"))
