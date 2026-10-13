"""Probe actual downloaded samples and make previews/configs without inference."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
inventory = []
for video in sorted((root / "inputs/uit-snippets").glob("*.mp4")):
    data = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames", "-show_entries", "format=duration,size",
        "-of", "json", str(video)]))
    inventory.append({"file": video.name, "metadata": data})
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "5", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=1280:-1", str(root / "outputs" / (video.stem + "-preview.jpg"))], check=True)
    config = {"camera_id": video.stem, "dataset": "UIT-ADrone selected public snippets",
              "video": str(video), "model": str(root / "models/yolo11m.pt"),
              "tracker": str(root / "configs/botsort-demo.yaml"), "imgsz": 1280, "confidence": .1,
              "iou": .5, "device": "0", "start_seconds": 0, "duration_seconds": 60,
              "frame_stride": 1, "bin_seconds": 5, "max_tracking_gap_seconds": .75,
              "line_margin_pixels": 3, "roi": [.32, .35, .83, 1],
              "vehicle_classes": ["car", "motorcycle", "bus", "truck"],
              "lines": [{"name": "south_approach", "start": [.39, .88], "end": [.77, .88],
                         "negative_to_positive": "away_from_roundabout", "positive_to_negative": "toward_roundabout"}],
              "road_mapping": None, "captured_at": None}
    if "_22_3_" in video.stem or "_31_3_" in video.stem:
        # These recordings rotate the same view. The south line from the first
        # recording is not a transferable camera configuration.
        config["roi"] = [.04, 0, .6, .65]
        config["lines"] = [{"name": "west_approach", "start": [.27, .06], "end": [.27, .51],
                            "negative_to_positive": "away_from_roundabout", "positive_to_negative": "toward_roundabout"}]
    (root / "configs" / (video.stem + ".json")).write_text(json.dumps(config, indent=2), encoding="utf-8")
(root / "outputs/sample-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
print(json.dumps(inventory, indent=2))
