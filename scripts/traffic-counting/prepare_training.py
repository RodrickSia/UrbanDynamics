"""Build a small, reproducible training subset from the dataset's TRAIN labels.

Training recordings DJI_0065/DJI_0148 differ from all three counting demo videos.
Validation is an internal frame split; it is not a camera-generalization claim.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-per-recording", type=int, default=80)
    parser.add_argument("--annotation-image-id-offset", type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "training-subset"
    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)
    data = json.loads((root / "inputs/uit-annotations/train.json").read_text())
    image_sets = {}
    for source in ("DJI_0065", "DJI_0148"):
        candidates = sorted((image for image in data["images"] if Path(image["file_name"]).parent.name == source),
                            key=lambda i: int(Path(i["file_name"]).stem))
        if len(candidates) < args.frames_per_recording:
            raise ValueError("Too few labeled training frames")
        image_sets[source] = [candidates[round(i*(len(candidates)-1)/(args.frames_per_recording-1))]
                              for i in range(args.frames_per_recording)]
    selected_ids = {image["id"] for images in image_sets.values() for image in images}
    labels = defaultdict(list)
    for annotation in data["annotations"]:
        adjusted_id = annotation["image_id"] + args.annotation_image_id_offset
        if adjusted_id in selected_ids:
            labels[adjusted_id].append(annotation)
    counts, class_counts, records = Counter(), Counter(), []
    del data
    for source, images in image_sets.items():
        capture = cv2.VideoCapture(str(root / "inputs/uit-training-videos" / (source + ".MP4")))
        if not capture.isOpened():
            raise ValueError("Training video cannot be opened")
        for index, image in enumerate(images):
            frame_number = int(Path(image["file_name"]).stem)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Labeled frame cannot be decoded: {source} {frame_number}")
            width, height = image["width"], image["height"]
            frame = cv2.resize(frame, (width, height))
            split = "val" if index % 5 == 0 else "train"
            if index == 0:
                preview = frame.copy()
                for ann in labels[image["id"]]:
                    x, y, w, h = map(int, ann["bbox"])
                    cv2.rectangle(preview, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(preview, str(ann["category_id"]), (x, y), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 1)
                cv2.imwrite(str(output / (source + "-label-alignment.jpg")), preview)
            for tile_y in range(2):
                for tile_x in range(2):
                    left, top = tile_x*width//2, tile_y*height//2
                    right, bottom = (tile_x+1)*width//2, (tile_y+1)*height//2
                    tile_labels = []
                    for ann in labels[image["id"]]:
                        x, y, w, h = ann["bbox"]
                        x1, y1, x2, y2 = max(left, x), max(top, y), min(right, x+w), min(bottom, y+h)
                        # Keep visible object fragments rather than teaching the
                        # detector that a cropped vehicle is empty background.
                        if x2-x1 < 2 or y2-y1 < 2 or (x2-x1)*(y2-y1) < .2*w*h:
                            continue
                        tile_labels.append(f"{ann['category_id']} {((x1+x2)/2-left)/(right-left):.7f} {((y1+y2)/2-top)/(bottom-top):.7f} {(x2-x1)/(right-left):.7f} {(y2-y1)/(bottom-top):.7f}")
                        class_counts[ann["category_id"]] += 1
                    name = f"{source}-{frame_number:06d}-{tile_x}{tile_y}"
                    cv2.imwrite(str(output / "images" / split / (name + ".jpg")), frame[top:bottom, left:right])
                    (output / "labels" / split / (name + ".txt")).write_text("\n".join(tile_labels), encoding="utf-8")
                    counts[split] += 1
            records.append({"source": source, "original_frame": frame_number, "image_id": image["id"], "split": split})
            if index % 20 == 0:
                print(source, index, "frames prepared", flush=True)
        capture.release()
    names = ["bus", "car", "bicycle", "pedestrian", "motorcycle", "truck", "tricycle", "van"]
    yaml = f"path: {output}\ntrain: images/train\nval: images/val\nnames:\n" + "".join(f"  {i}: {name}\n" for i, name in enumerate(names))
    (output / "dataset.yaml").write_text(yaml, encoding="utf-8")
    manifest = {"source_label_file": "inputs/uit-annotations/train.json", "records": records,
                "annotation_image_id_offset": args.annotation_image_id_offset,
                "tile_counts": dict(counts), "label_counts": dict(class_counts), "names": names,
                "counting_demo_recordings_excluded": ["50m_90d_morning_congkhuA_16_3", "50m_90d_morning_congkhuA_22_3", "50m_90d_morning_congkhuA_31_3"],
                "limitations": "Internal split shares recordings, adjacent frames correlated. Tile annotations clipped to visible boxes (minimum 20% retained area); small exploratory subset, not official benchmark."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
