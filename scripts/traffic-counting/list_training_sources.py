import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "inputs/uit-annotations/train.json").read_text())
print(json.dumps({"categories": data["categories"], "images": len(data["images"]), "annotations": len(data["annotations"]),
                  "recording_frames": dict(Counter(str(Path(image["file_name"]).parent) for image in data["images"]))}, indent=2))
