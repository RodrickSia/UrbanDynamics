"""Report COCO indexing and explicit correction, retaining downloaded originals."""
from collections import Counter
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = {"verified_offset_for_selected_samples": -1,
          "evidence": ["Image ID zero has visible vehicles but annotations begin with image_id one.",
                       "Visual overlays on demo frames and DJI_0065 training frame align after image_id - 1.",
                       "Public reference JPEG 000005.jpg also checked against decoded snippet frames."],
          "limitations": "Visual checks cover selected records, not every label; original files unchanged. This is a local ingest correction, not a publisher revision.",
          "files": {}}
for split in ("train", "test"):
    data = json.loads((root / "inputs/uit-annotations" / (split + ".json")).read_text())
    images = {image["id"] for image in data["images"]}
    ids = Counter(ann["image_id"] for ann in data["annotations"])
    report["files"][split] = {"images": len(images), "annotations": len(data["annotations"]),
                               "image_id_min": min(images), "image_id_max": max(images),
                               "annotation_image_id_min": min(ids), "annotation_image_id_max": max(ids),
                               "raw_orphan_annotations": sum(count for key, count in ids.items() if key not in images),
                               "offset_minus_one_orphan_annotations": sum(count for key, count in ids.items() if key-1 not in images)}
    del data
(root / "outputs/dataset-index-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
