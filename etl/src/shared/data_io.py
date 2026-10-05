"""Bounded downloads, provenance and atomic local snapshots."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def data_dir():
    return Path(os.getenv("DATA_DIR", "data")).resolve()


def session():
    client = requests.Session()
    client.headers["User-Agent"] = "UrbanDynamics/0.1 public-data-research"
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=0.5, status_forcelist=[429, 502, 503, 504])))
    return client


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def file_provenance(path, url=None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(65536), b""):
            digest.update(block)
    return {"url":url,"sha256":digest.hexdigest(),"bytes":path.stat().st_size,
            "ingested_at":utc_now(),"path":str(path),"cached_source":True}


def download(url, path, max_bytes=100_000_000):
    """Replace a cached original only after a complete successful download."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".download")
    size = 0
    digest = hashlib.sha256()
    try:
        with session().get(url, stream=True, timeout=(20, 120)) as response:
            response.raise_for_status()
            with os.fdopen(handle, "wb") as stream:
                for block in response.iter_content(65536):
                    size += len(block)
                    if size > max_bytes:
                        raise ValueError(f"Download exceeds {max_bytes} bytes")
                    stream.write(block)
                    digest.update(block)
        if not size:
            raise ValueError("Empty download")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"url": url, "sha256": digest.hexdigest(), "bytes": size,
            "ingested_at": utc_now(), "path": str(path)}


def collection(layer, features, **metadata):
    return {"type": "FeatureCollection", "features": features,
            "metadata": {"layer": layer, "ingested_at": utc_now(), **metadata}}
