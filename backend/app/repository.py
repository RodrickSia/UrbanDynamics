"""One read interface for local snapshots and PostGIS."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from shapely.geometry import shape, box

LAYERS = ("flood_history", "flood_satellite", "flood_satellite_catalog", "flood_risk", "land_price")

class LayerUnavailable(Exception):
    pass

def directory():
    return Path(os.getenv("DATA_DIR", "data")).resolve()

def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)

def metadata(layer):
    url = os.getenv("DATABASE_URL")
    if url:
        import psycopg
        with psycopg.connect(url) as connection:
            row = connection.execute("SELECT metadata FROM layer_snapshots WHERE layer=%s", (layer,)).fetchone()
            if row is None:
                raise LayerUnavailable(layer)
            return freshness(row[0])
    path = directory() / "layers" / f"{layer}.geojson"
    if not path.exists():
        raise LayerUnavailable(layer)
    return freshness(json.loads(path.read_text(encoding="utf-8"))["metadata"])

def freshness(info):
    info = dict(info)
    if info.get("expires_at"):
        info["stale"] = datetime.now(timezone.utc) >= instant(info["expires_at"])
    return info

def features(layer, bounds=None, start=None, end=None, limit=5000):
    info = metadata(layer)
    url = os.getenv("DATABASE_URL")
    if url:
        import psycopg
        clauses, arguments = ["layer=%s"], [layer]
        if bounds:
            clauses.append("ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,4326))")
            arguments.extend(bounds)
        if start:
            clauses.append("observed_at >= %s")
            arguments.append(start)
        if end:
            clauses.append("observed_at < %s")
            arguments.append(end)
        arguments.append(limit+1)
        with psycopg.connect(url) as connection:
            rows = connection.execute("SELECT feature_id,ST_AsGeoJSON(geom),properties FROM layer_features WHERE "
                                      + " AND ".join(clauses) + " ORDER BY feature_id LIMIT %s", arguments).fetchall()
        matches = [{"type": "Feature", "id": row[0], "geometry": json.loads(row[1]), "properties": row[2]} for row in rows]
    else:
        document = json.loads((directory() / "layers" / f"{layer}.geojson").read_text(encoding="utf-8"))
        matches = []
        viewport = box(*bounds) if bounds else None
        for feature in sorted(document["features"], key=lambda f: str(f["id"])):
            if viewport is not None and not shape(feature["geometry"]).intersects(viewport):
                continue
            date = feature["properties"].get("observed_at")
            if (start or end) and (date is None or start and instant(date) < start or end and instant(date) >= end):
                continue
            matches.append(feature)
            if len(matches) > limit:
                break
    return {"type": "FeatureCollection", "features": matches[:limit],
            "metadata": {**info, "truncated": len(matches) > limit, "returned": min(len(matches), limit)}}

def readiness():
    if os.getenv("DATABASE_URL"):
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute("SELECT 1")
            count = connection.execute("SELECT count(*) FROM layer_snapshots").fetchone()[0]
        return {"storage": "postgis", "loaded_layers": count}
    return {"storage": "snapshots", "loaded_layers": len(list((directory() / "layers").glob("*.geojson")))}
