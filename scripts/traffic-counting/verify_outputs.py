"""Verify generated artifacts and conservation, without asserting counting accuracy."""
import argparse
import csv
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runs-dir", default="outputs/visdrone-pretrained")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
runs = root / args.runs_dir
checks = []
for path in sorted(runs.glob("50m*/summary.json")):
    summary = json.loads(path.read_text())
    folder = path.parent
    with (folder / "events.csv").open() as stream:
        events = list(csv.DictReader(stream))
    with (folder / "counts.csv").open() as stream:
        bins = list(csv.DictReader(stream))
    tracks = sum(1 for _ in (folder / "tracks.jsonl").open())
    video = folder / "demo.mp4"
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=codec_name,nb_frames,width,height", "-of", "json", str(video)]))["streams"][0]
    assert len(events) == summary["total_crossings"] == sum(int(row["count"]) for row in bins)
    assert len(events) == sum(row["count"] for row in summary["counts"])
    assert tracks == int(info["nb_frames"]) == summary["observation"]["processed_frames"]
    assert all(summary["observation"]["start_video_seconds"] <= float(row["video_seconds"]) <
               summary["observation"]["end_video_seconds"] for row in events)
    assert info["codec_name"] == "h264"
    checks.append({"camera_id": summary["camera_id"], "events": len(events), "frames": tracks,
                   "artifact_checks": "passed", "counting_accuracy": None})
if len(checks) != 3:
    raise ValueError(f"Expected three completed samples, found {len(checks)}")
(runs / "artifact-checks.json").write_text(json.dumps(checks, indent=2))
print(json.dumps(checks, indent=2))
