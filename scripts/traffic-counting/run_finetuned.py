import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--run-name", default="fine-tuned")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
model = root / "training-runs/uit-demo/weights/best.pt"
if not model.is_file():
    raise ValueError("Fine-tuned checkpoint unavailable")
for original_config in sorted((root / "configs").glob("50m*.json")):
    config = json.loads(original_config.read_text())
    config["model"] = str(model)
    config["vehicle_classes"] = ["bus", "car", "bicycle", "motorcycle", "truck", "tricycle", "van"]
    config_path = root / "configs" / (config["camera_id"] + "-fine-tuned.json")
    if original_config.name.endswith("-fine-tuned.json"):
        continue
    config_path.write_text(json.dumps(config, indent=2))
    subprocess.run([sys.executable, str(root / "scripts/run_counting.py"), "--config", str(config_path),
                    "--output", str(root / "outputs" / args.run_name / config["camera_id"])], check=True)
