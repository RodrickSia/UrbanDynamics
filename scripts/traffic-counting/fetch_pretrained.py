"""Download a revision-pinned public aerial detector, without training."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", default="dronefreak/visdrone-yolov8m")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
metadata = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{args.repo}", timeout=30))
revision = metadata["sha"]
if "best.pt" not in {item["rfilename"] for item in metadata["siblings"]}:
    raise ValueError("Publisher has no best.pt checkpoint")
folder = root / "models" / args.repo.replace("/", "--")
folder.mkdir(exist_ok=True)
url = f"https://huggingface.co/{args.repo}/resolve/{revision}/best.pt"
target = folder / "best.pt"
if not target.exists():
    partial = folder / "best.pt.part"
    urllib.request.urlretrieve(url, partial)
    partial.replace(target)
digest = hashlib.sha256(target.read_bytes()).hexdigest()
card = urllib.request.urlopen(f"https://huggingface.co/{args.repo}/raw/{revision}/README.md", timeout=30).read()
(folder / "README.source.md").write_bytes(card)
manifest = {"repo": args.repo, "revision": revision, "url": url,
            "sha256": digest, "bytes": target.stat().st_size,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "card_data": metadata.get("cardData"),
            "local_training": False, "checkpoint": str(target)}
(folder / "source-manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps({key: manifest[key] for key in ("repo", "revision", "sha256", "bytes", "checkpoint")}, indent=2))
