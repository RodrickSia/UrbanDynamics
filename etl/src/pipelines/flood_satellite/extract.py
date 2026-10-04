import re
from src.shared.data_io import data_dir, download, session
from .config import STAC_URL, FLOOD_ASSET, MASK_ASSET, MAX_ITEMS

def run(boundary, catalog_only=False, limit=MAX_ITEMS):
    response = session().get(STAC_URL, params={"bbox": ",".join(map(str, boundary.bounds)),
                                              "limit": limit}, timeout=(20, 90))
    response.raise_for_status()
    items = response.json()["features"]
    results = []
    for item in items:
        identifier = re.sub(r"[^a-zA-Z0-9_-]", "_", item["id"])
        paths, provenance = {}, []
        if not catalog_only:
            for key in (FLOOD_ASSET, MASK_ASSET):
                if key not in item.get("assets", {}):
                    if key == MASK_ASSET:
                        continue
                    raise ValueError(f"Missing {key}; cannot verify observed flood pixels")
                path = data_dir() / "raw" / "flood_satellite" / identifier / f"{key}.tif"
                provenance.append(download(item["assets"][key]["href"], path))
                paths[key] = path
        results.append({"item": item, "paths": paths, "provenance": provenance})
    return results
