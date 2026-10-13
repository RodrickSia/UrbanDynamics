from collections import defaultdict
import json
from pathlib import Path
import cv2

root = Path(__file__).resolve().parents[1]
data = json.loads((root / "inputs/uit-annotations/test.json").read_text())
images = {image["id"]: image for image in data["images"] if Path(image["file_name"]).parent.name == "50m_90d_morning_congkhuA_16_3" and int(Path(image["file_name"]).stem) < 100}
labels = defaultdict(list)
for ann in data["annotations"]:
    if ann["image_id"]-1 in images:
        labels[ann["image_id"]-1].append(ann)
print("First frame labels:", [(i, images[i]["file_name"], len(labels[i])) for i in sorted(images)[:10]])
cap = cv2.VideoCapture(str(root / "inputs/uit-snippets/50m_90d_morning_congkhuA_16_3_0.mp4"))
for index, image_id in enumerate([i for i in sorted(images) if labels[i]][:3]):
    frame_index = int(Path(images[image_id]["file_name"]).stem)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    if ok:
        for ann in labels[image_id]:
            x, y, w, h = map(int, ann["bbox"])
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 255), 2)
            cv2.putText(frame, str(ann["category_id"]), (x, y), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 0, 255), 1)
        cv2.imwrite(str(root / "outputs" / f"test-alignment-minus1-{index}.jpg"), frame)
cap.release()
