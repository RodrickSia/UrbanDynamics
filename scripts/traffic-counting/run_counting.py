"""Standalone video vehicle counting with real YOLO detection and persistent tracking."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time

from count_core import Line, aggregate


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import cv2
    import torch
    import ultralytics
    from ultralytics import YOLO

    torch.set_num_threads(4)
    cv2.setNumThreads(2)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    video = Path(config["video"])
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    width, height = (int(capture.get(key)) for key in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
    available_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(fps) or fps <= 0 or width < 1 or height < 1:
        raise ValueError("Video lacks valid dimensions/time base")
    stride = int(config.get("frame_stride", 1))
    if stride < 1:
        raise ValueError("frame_stride must be positive")
    first = int(config.get("start_seconds", 0) * fps)
    stop = min(available_frames, first + int(config.get("duration_seconds", 60)*fps))
    if not 0 <= first < stop:
        raise ValueError("Requested observation window is outside the video")
    line_configs = config["lines"]
    if not line_configs or len({item["name"] for item in line_configs}) != len(line_configs):
        raise ValueError("Require uniquely named counting lines")
    for item in line_configs:
        if any(not 0 <= coordinate <= 1 for point in (item["start"], item["end"]) for coordinate in point):
            raise ValueError("Line coordinates must be normalized between zero and one")
    lines = [Line(item["name"], (item["start"][0]*width, item["start"][1]*height),
                  (item["end"][0]*width, item["end"][1]*height),
                  item.get("negative_to_positive", "negative_to_positive"),
                  item.get("positive_to_negative", "positive_to_negative"), config.get("line_margin_pixels", 3))
             for item in line_configs]
    roi = config.get("roi", [0, 0, 1, 1])
    if len(roi) != 4 or not 0 <= roi[0] < roi[2] <= 1 or not 0 <= roi[1] < roi[3] <= 1:
        raise ValueError("ROI requires normalized left/top/right/bottom")
    left, top, right, bottom = [int(value*dimension) for value, dimension in zip(roi, (width, height, width, height))]
    max_gap = max(1, round(config.get("max_tracking_gap_seconds", 1) * fps))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    model = YOLO(config.get("model", "yolo11m.pt"))
    aliases = config.get("class_aliases", {})
    class_names = config.get("vehicle_classes", ["car", "motorcycle", "bus", "truck"])
    selected = [key for key, value in model.names.items() if aliases.get(value, value) in class_names]
    if not selected:
        raise ValueError("No requested classes in model")
    writer = cv2.VideoWriter(str(out / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps/stride, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Annotated video writer unavailable")
    votes, confidence_totals, observations = defaultdict(Counter), defaultdict(float), Counter()
    events, totals, tracked_counts = [], Counter(), []
    started = time.perf_counter()
    capture.set(cv2.CAP_PROP_POS_FRAMES, first)
    processed, last_frame, frame_index = 0, first-1, first
    tracks_stream = (out / "tracks.jsonl").open("w", encoding="utf-8")
    try:
        while frame_index < stop:
            ok, frame = capture.read()
            if not ok:
                break
            last_frame = frame_index
            if (frame_index-first) % stride:
                frame_index += 1
                continue
            crop = frame[top:bottom, left:right]
            result = model.track(crop, persist=True, tracker=config.get("tracker", "botsort.yaml"),
                                 conf=config.get("confidence", .15), iou=config.get("iou", .5),
                                 imgsz=config.get("imgsz", 1280), classes=selected,
                                 device=config.get("device", "0" if torch.cuda.is_available() else "cpu"), verbose=False)[0]
            current_tracks = []
            boxes = result.boxes
            if boxes is not None and boxes.id is not None:
                for box, track_id, class_id, confidence in zip(boxes.xyxy.cpu().tolist(), boxes.id.int().cpu().tolist(),
                                                              boxes.cls.int().cpu().tolist(), boxes.conf.cpu().tolist()):
                    name = aliases.get(model.names[class_id], model.names[class_id])
                    votes[track_id][name] += confidence
                    stable_name = votes[track_id].most_common(1)[0][0]
                    confidence_totals[track_id] += confidence
                    observations[track_id] += 1
                    x1, y1, x2, y2 = box[0]+left, box[1]+top, box[2]+left, box[3]+top
                    center = ((x1+x2)/2, (y1+y2)/2)
                    current_tracks.append({"id": track_id, "vehicle_class": stable_name, "confidence": confidence,
                                           "box_xyxy": [x1, y1, x2, y2], "center": center})
                    for line in lines:
                        event = line.update(track_id, center, frame_index, max_gap)
                        if event:
                            event.update(video_seconds=event["frame"]/fps, vehicle_class=stable_name,
                                         detection_confidence=confidence,
                                         mean_track_confidence=confidence_totals[track_id]/observations[track_id])
                            events.append(event)
                            totals[(line.name, event["direction"], stable_name)] += 1
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (50, 220, 50), 1)
                    cv2.putText(frame, f"{track_id}:{stable_name}", (int(x1), int(y1)-3), cv2.FONT_HERSHEY_SIMPLEX, .35, (40, 240, 40), 1)
            for line in lines:
                line.prune(frame_index, max_gap)
                cv2.line(frame, tuple(map(int, line.start)), tuple(map(int, line.end)), (0, 220, 255), 3)
                cv2.putText(frame, line.name, tuple(map(int, line.start)), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 220, 255), 2)
            hud_x = max(0, width-560)
            cv2.rectangle(frame, (hud_x, 0), (width, min(145, height)), (25, 25, 25), -1)
            cv2.putText(frame, f"t={frame_index/fps:.2f}s | detected crossings={len(events)}", (hud_x+12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2)
            for row, ((line_name, direction, name), count) in enumerate(sorted(totals.items())[:4]):
                cv2.putText(frame, f"{direction} {name}: {count}", (hud_x+12, 52 + 20*row), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
            tracks_stream.write(json.dumps({"frame": frame_index, "video_seconds": frame_index/fps, "tracks": current_tracks})+"\n")
            writer.write(frame)
            if processed % max(1, round(fps*5)) == 0:
                cv2.imwrite(str(out / "latest-preview.jpg"), frame)
                print(json.dumps({"video_seconds": round(frame_index/fps, 2), "events": len(events), "tracked": len(current_tracks)}), flush=True)
            tracked_counts.append(len(current_tracks))
            processed += 1
            frame_index += 1
    finally:
        tracks_stream.close()
        capture.release()
        writer.release()
    if not processed:
        raise RuntimeError("No decoded frames processed")
    end_seconds = (last_frame+1)/fps
    bins = aggregate(events, first/fps, end_seconds, config.get("bin_seconds", 15))
    write_csv(out / "events.csv", events, ["line_id", "direction", "vehicle_class", "track_id", "frame", "video_seconds", "detection_confidence", "mean_track_confidence"])
    write_csv(out / "counts.csv", bins, ["line_id", "direction", "vehicle_class", "start_video_seconds", "end_video_seconds", "observed_seconds", "count", "extrapolated_vehicles_hour", "rate_kind"])
    summary = {"schema_version": "traffic-counts-1", "camera_id": config["camera_id"], "dataset": config.get("dataset"),
               "created_at": datetime.now(timezone.utc).isoformat(), "source_video": str(video), "source_sha256": sha256(video),
               "video": {"width": width, "height": height, "fps": fps, "total_frames": available_frames},
               "observation": {"start_video_seconds": first/fps, "end_video_seconds": end_seconds, "duration_seconds": end_seconds-first/fps,
                               "processed_frames": processed, "frame_stride": stride},
               "config": config, "runtime": {"torch": torch.__version__, "ultralytics": ultralytics.__version__,
                    "cuda_available": torch.cuda.is_available(), "seconds": time.perf_counter()-started,
                    "processed_frames_per_second": processed/(time.perf_counter()-started)},
               "total_crossings": len(events), "counts": [{"line_id": key[0], "direction": key[1], "vehicle_class": key[2], "count": value}
                                                          for key, value in sorted(totals.items())],
               "mean_tracked_vehicles_frame": sum(tracked_counts)/len(tracked_counts),
               "validation": {"status": "not_manually_validated", "accuracy": None},
               "simulation_ready": False, "limitations": ["Pretrained detector; counting accuracy requires independent labels.",
                    "Track fragmentation may over/undercount; per-track dedup does not identify physical vehicles across new IDs.",
                    "Fixed image counting lines require a stationary or stabilized view; tracker GMC alone does not stabilize the line.",
                    "Short windows do not establish hourly/daily OD or recent site flows; direction labels require camera-to-road mapping."]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
