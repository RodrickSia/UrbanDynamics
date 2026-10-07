from src.shared.data_io import data_dir,read_json,write_json
from src.shared.database import publish
from .transform import layer

def input_pair(root=None):
    root = root or data_dir()
    pointer = root/"inputs/rainwater_current.json"
    if pointer.exists():
        run_id = read_json(pointer)["run_id"]
        if len(run_id)!=32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid rain snapshot ID")
        base = root/"inputs/rainwater/runs"/run_id
        return read_json(base/"forecast.json"),read_json(base/"history.json")
    return read_json(root/"inputs/rainwater_forecast.json"),read_json(root/"inputs/rainwater_history.json")

def run(forecast,history):
    document = layer(forecast,history)
    root = data_dir(); base = root/"inputs/rainwater/runs"/forecast["run_id"]
    write_json(base/"forecast.json",forecast); write_json(base/"history.json",history)
    result = publish("rainwater",document)
    write_json(root/"inputs/rainwater_current.json",{"run_id":forecast["run_id"]})
    write_json(root/"inputs/rainwater_forecast.json",forecast)
    write_json(root/"inputs/rainwater_history.json",history)
    return result
