"""Summarize actual COCO fields and counting suitability without dumping labels."""
from collections import Counter
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with (root / "inputs/uit-annotations/test.json").open() as stream:
    data = json.load(stream)
annotations = data.get("annotations", [])
summary = {"keys": list(data), "categories": data.get("categories"),
           "images_count": len(data.get("images", [])), "annotations_count": len(annotations),
           "annotation_keys": sorted({key for ann in annotations[:1000] for key in ann}),
           "images_sample": data.get("images", [])[:3],
           "category_annotation_counts": dict(Counter(a["category_id"] for a in annotations)),
           "annotations_with_track_id": sum("track_id" in a or "instance_id" in a for a in annotations),
           "counting_labels_available": False,
           "note": "COCO detections/anomaly labels do not themselves provide directed line-crossing counts. Check image/video matching before evaluation."}
(root / "outputs/annotation-inventory.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
