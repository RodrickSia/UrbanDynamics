"""Inspect raw pretrained classes to diagnose a zero-count scene."""
from collections import Counter
import argparse
import json
from pathlib import Path
import cv2
from ultralytics import YOLO
import torch

torch.set_num_threads(4)
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--model", default="models/yolo11m.pt")
parser.add_argument("--prefix", default="raw")
args = parser.parse_args()
model = YOLO(root / args.model)
report = []
for config_file in sorted((root / "configs").glob("50m*.json")):
    if config_file.stem not in {path.stem for path in (root / "inputs/uit-snippets").glob("*.mp4")}:
        continue
    config = json.loads(config_file.read_text())
    capture = cv2.VideoCapture(config["video"])
    capture.set(cv2.CAP_PROP_POS_MSEC, 5000)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        continue
    h, w = frame.shape[:2]
    left, top, right, bottom = [int(x*d) for x, d in zip(config["roi"], (w, h, w, h))]
    result = model.predict(frame[top:bottom, left:right], device="0", imgsz=1280, conf=.05, verbose=False)[0]
    report.append({"sample": config["camera_id"], "raw_classes": dict(Counter(model.names[int(c)] for c in result.boxes.cls)),
                   "detections": [{"class": model.names[int(c)], "conf": float(score)} for c, score in zip(result.boxes.cls, result.boxes.conf)],
                   "timing_ms": result.speed})
    cv2.imwrite(str(root / "outputs" / (config["camera_id"] + "-" + args.prefix + "-detection.jpg")), result.plot())
(root / "outputs" / (args.prefix + "-detection-check.json")).write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
