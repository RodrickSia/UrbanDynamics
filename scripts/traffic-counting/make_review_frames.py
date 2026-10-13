"""Unannotated source filmstrips around the line for independent manual checking."""
import json
from pathlib import Path
import cv2
import numpy as np

root = Path(__file__).resolve().parents[1]
for config_file in sorted((root / "configs").glob("50m*.json")):
    if config_file.name.endswith("-fine-tuned.json"):
        continue
    config = json.loads(config_file.read_text())
    cap = cv2.VideoCapture(config["video"])
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps, total = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    item = config["lines"][0]
    a = tuple(round(v*d) for v, d in zip(item["start"], (width, height)))
    b = tuple(round(v*d) for v, d in zip(item["end"], (width, height)))
    if abs(a[0]-b[0]) < abs(a[1]-b[1]):
        bounds = [max(0, a[0]-140), max(0, min(a[1], b[1])-30), min(width, a[0]+140), min(height, max(a[1], b[1])+30)]
        thumb_size = (200, 360)
        columns = 8
    else:
        bounds = [max(0, min(a[0], b[0])-30), max(0, a[1]-120), min(width, max(a[0], b[0])+30), min(height, a[1]+120)]
        thumb_size = (400, 135)
        columns = 4
    cells = []
    for frame_index in range(0, total, max(1, round(fps*.25))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            continue
        cv2.line(frame, a, b, (0, 255, 255), 1)
        left, top, right, bottom = bounds
        thumb = cv2.resize(frame[top:bottom, left:right], thumb_size)
        cv2.putText(thumb, f"t={frame_index/fps:.2f}s", (5, 17), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
        cells.append(thumb)
    cap.release()
    rows = (len(cells)+columns-1)//columns
    canvas = np.full((rows*thumb_size[1], columns*thumb_size[0], 3), 245, np.uint8)
    for index, cell in enumerate(cells):
        y, x = (index//columns)*thumb_size[1], (index%columns)*thumb_size[0]
        canvas[y:y+thumb_size[1], x:x+thumb_size[0]] = cell
    cv2.imwrite(str(root / "outputs" / (config["camera_id"] + "-manual-review.jpg")), canvas)
    print(config["camera_id"], len(cells), "raw frames", flush=True)
