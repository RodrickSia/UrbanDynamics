"""Evaluate tracked boxes against downloaded COCO labels, NOT counting accuracy."""
from collections import defaultdict
import argparse
import json
from pathlib import Path

import cv2


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default="outputs")
    parser.add_argument("--annotation-image-id-offset", type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runs = root / args.runs_dir
    data = json.loads((root / "inputs/uit-annotations/test.json").read_text())
    reports, matched_images = [], {}
    for summary_file in sorted(runs.glob("50m*/summary.json")):
        summary = json.loads(summary_file.read_text())
        original = summary["camera_id"].rsplit("_", 1)[0]
        frames = {int(Path(image["file_name"]).stem): image for image in data["images"]
                  if Path(image["file_name"]).parent.name == original and int(Path(image["file_name"]).stem) < summary["video"]["total_frames"]}
        matched_images.update({image["id"]: (summary["camera_id"], frame) for frame, image in frames.items()})
        reports.append({"camera_id": summary["camera_id"], "frame_map": frames, "summary": summary})
    labels = defaultdict(list)
    classes = {0: "bus", 1: "light_vehicle", 4: "motorcycle", 5: "truck", 7: "light_vehicle"}
    for annotation in data["annotations"]:
        adjusted_id = annotation["image_id"] + args.annotation_image_id_offset
        if adjusted_id in matched_images and annotation["category_id"] in classes:
            x, y, w, h = annotation["bbox"]
            labels[matched_images[adjusted_id]].append({"class": classes[annotation["category_id"]], "box": [x, y, x+w, y+h]})
    del data
    output = []
    for report in reports:
        camera, summary, frames = report["camera_id"], report["summary"], report["frame_map"]
        roi = [value*dimension for value, dimension in zip(summary["config"]["roi"],
                                                         (summary["video"]["width"], summary["video"]["height"])*2)]
        records = [json.loads(line) for line in (runs / camera / "tracks.jsonl").read_text().splitlines()]
        metrics = {threshold: defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0}) for threshold in (.3, .5)}
        evaluated = 0
        for record in records:
            frame = record["frame"]
            if frame not in frames:
                continue
            expected = [ann for ann in labels[(camera, frame)] if roi[0] <= ann["box"][0] and roi[1] <= ann["box"][1]
                        and ann["box"][2] <= roi[2] and ann["box"][3] <= roi[3]]
            predictions = [{"class": "light_vehicle" if t["vehicle_class"] in ("car", "van") else t["vehicle_class"], "box": t["box_xyxy"]}
                           for t in record["tracks"] if t["vehicle_class"] in ("car", "van", "bus", "truck", "motorcycle")
                           and roi[0] <= t["box_xyxy"][0] and roi[1] <= t["box_xyxy"][1]
                           and t["box_xyxy"][2] <= roi[2] and t["box_xyxy"][3] <= roi[3]]
            for threshold, classes_metrics in metrics.items():
                proposals = sorted(((iou(pred["box"], ann["box"]), p, g) for p, pred in enumerate(predictions)
                                     for g, ann in enumerate(expected) if pred["class"] == ann["class"]), reverse=True)
                used_p, used_g = set(), set()
                for overlap, p, g in proposals:
                    if overlap >= threshold and p not in used_p and g not in used_g:
                        used_p.add(p)
                        used_g.add(g)
                        classes_metrics[predictions[p]["class"]]["tp"] += 1
                for p, pred in enumerate(predictions):
                    if p not in used_p:
                        classes_metrics[pred["class"]]["fp"] += 1
                for g, ann in enumerate(expected):
                    if g not in used_g:
                        classes_metrics[ann["class"]]["fn"] += 1
            if frame == min(frames):
                cap = cv2.VideoCapture(summary["source_video"])
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
                ok, preview = cap.read()
                cap.release()
                if ok:
                    for collection, color in ((expected, (255, 0, 255)), (predictions, (0, 255, 0))):
                        for item in collection:
                            x1, y1, x2, y2 = map(int, item["box"])
                            cv2.rectangle(preview, (x1, y1), (x2, y2), color, 2)
                            cv2.putText(preview, item["class"], (x1, y1), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
                    cv2.imwrite(str(runs / camera / "label-alignment.jpg"), preview)
            evaluated += 1
        for classes_metrics in metrics.values():
            for values in classes_metrics.values():
                values["precision"] = values["tp"] / (values["tp"]+values["fp"]) if values["tp"]+values["fp"] else None
                values["recall"] = values["tp"] / (values["tp"]+values["fn"]) if values["tp"]+values["fn"] else None
        output.append({"camera_id": camera, "evaluated_labeled_frames": evaluated,
                       "annotation_image_id_offset": args.annotation_image_id_offset,
                       "tracked_box_metrics": dict(metrics), "counting_accuracy": None,
                       "matching": "Class-aware greedy one-to-one IoU, fully-contained boxes within configured ROI; car and van grouped as light_vehicle",
                       "limitations": "Sequential labeled frames are correlated. No confidence interval, no count accuracy, no tracking-ID truth. Visually verify source alignment before interpreting metrics."})
    (runs / "detection-check.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
