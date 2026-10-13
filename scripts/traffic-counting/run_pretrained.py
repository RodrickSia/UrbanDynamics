"""Run all selected clips with a downloaded aerial checkpoint; no local training."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-name", default="visdrone-pretrained")
parser.add_argument("--model", default="models/dronefreak--visdrone-yolov8m/best.pt")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
model = root / args.model
if not model.is_file():
    raise ValueError("Download the checkpoint using fetch_pretrained.py first")
for video in sorted((root / "inputs/uit-snippets").glob("*.mp4")):
    original = root / "configs" / (video.stem + ".json")
    config = json.loads(original.read_text())
    config.update(model=str(model), vehicle_classes=["car", "van", "bus", "truck", "motorcycle"],
                  class_aliases={"motor": "motorcycle"}, local_training=False)
    config_path = root / "configs" / (video.stem + "-" + args.run_name + ".json")
    config_path.write_text(json.dumps(config, indent=2))
    subprocess.run([sys.executable, str(root / "scripts/run_counting.py"), "--config", str(config_path),
                    "--output", str(root / "outputs" / args.run_name / video.stem)], check=True)
