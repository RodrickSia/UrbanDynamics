"""Download selected public UIT-ADrone files, retaining source and SHA-256.

Does not crawl the whole dataset or treat anomaly labels as traffic count truth.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request

ROOT_FOLDER = "1ygWcuOZ7kEwS-rC35gWv6f6qeNx0BHyg"
VIDEO_FOLDER = "1Q5NSEGnR3cgUm6S8WtKIg4mfS3-PO0bZ"


class Items(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        identifier, tooltip = attrs.get("data-id"), attrs.get("data-tooltip")
        if identifier and tooltip:
            self.items[identifier] = tooltip


def listing(folder):
    url = f"https://drive.google.com/drive/folders/{folder}"
    with urllib.request.urlopen(url, timeout=60) as response:
        page = response.read().decode("utf-8")
    parser = Items()
    parser.feed(page)
    return [{"id": key, "description": value} for key, value in parser.items.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", default=VIDEO_FOLDER)
    parser.add_argument("--output", default="inputs/uit-adrone")
    parser.add_argument("--download", nargs="*", default=[])
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    files = listing(args.folder)
    print(json.dumps(files, indent=2), flush=True)
    (out / "public-file-list.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    if not args.download:
        return
    import gdown
    manifest_path = out / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"dataset": "UIT-ADrone", "files": []}
    manifest.update(source_page="https://uit-together.github.io/datasets/UIT-ADrone/",
                    source_folder=f"https://drive.google.com/drive/folders/{args.folder}",
                    scope="Selected samples, not complete dataset", license_status="Not established from the public dataset page")
    for requested in args.download:
        matches = [f for f in files if f["description"].split(" ")[0] == requested or f["id"] == requested]
        if len(matches) != 1:
            raise ValueError(f"Expected one public file for {requested}, found {len(matches)}")
        item = matches[0]
        # Public names are simple names. Never allow a remote name to choose paths.
        name = item["description"].split(" ")[0]
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Unsafe dataset filename")
        destination = out / name
        if not destination.exists():
            result = gdown.download(id=item["id"], output=str(destination), quiet=False)
            if not result:
                raise RuntimeError(f"Download unavailable: {name}")
        sha = hashlib.sha256()
        with destination.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                sha.update(chunk)
        manifest["files"] = [f for f in manifest["files"] if f["name"] != name]
        manifest["files"].append({"name": name, "drive_id": item["id"], "bytes": destination.stat().st_size,
                                  "sha256": sha.hexdigest(), "fetched_at": datetime.now(timezone.utc).isoformat()})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Downloaded", name, destination.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
