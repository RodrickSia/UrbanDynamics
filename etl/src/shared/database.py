"""Atomic snapshot publication, optional transactional PostGIS writer."""
import json
import os
from pathlib import Path
from shapely.geometry import shape
from .data_io import data_dir, write_json

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS layer_snapshots (
    layer text PRIMARY KEY, metadata jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS layer_features (
    layer text NOT NULL REFERENCES layer_snapshots(layer),
    feature_id text NOT NULL, geom geometry(Geometry,4326) NOT NULL,
    properties jsonb NOT NULL, observed_at timestamptz,
    PRIMARY KEY (layer, feature_id)
);
CREATE INDEX IF NOT EXISTS layer_features_geom_idx ON layer_features USING gist(geom);
CREATE INDEX IF NOT EXISTS layer_features_time_idx ON layer_features(layer, observed_at);
"""


def publish(layer, document, root=None):
    features = document["features"]
    identifiers = [str(f["id"]) for f in features]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate feature IDs; snapshot not published")
    for feature in features:
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Invalid output geometry; snapshot not published")
    json.dumps(document, allow_nan=False)
    url = os.getenv("DATABASE_URL")
    if url:
        import psycopg
        from psycopg.types.json import Jsonb
        # Bootstrap DDL in a separate committed transaction. Running CREATE INDEX
        # inside concurrent snapshot writes would retain SHARE locks and deadlock
        # when both transactions later acquire RowExclusive locks for DELETE.
        with psycopg.connect(url) as bootstrap:
            bootstrap.execute("SELECT pg_advisory_xact_lock(hashtext('urban_layer_schema'))")
            bootstrap.execute(SCHEMA)
        with psycopg.connect(url) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (layer,))
            connection.execute("INSERT INTO layer_snapshots(layer,metadata) VALUES (%s,%s) "
                               "ON CONFLICT(layer) DO UPDATE SET metadata=excluded.metadata,updated_at=now()",
                               (layer, Jsonb(document["metadata"])))
            connection.execute("DELETE FROM layer_features WHERE layer=%s", (layer,))
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO layer_features(layer,feature_id,geom,properties,observed_at) "
                    "VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s,%s)",
                    [(layer, str(f["id"]), json.dumps(f["geometry"]), Jsonb(f["properties"]),
                      f["properties"].get("observed_at")) for f in features])
    target = (Path(root) if root else data_dir()) / "layers" / f"{layer}.geojson"
    write_json(target, document)
    return {"layer": layer, "features": len(features), "snapshot": str(target),
            "postgis": bool(url), "metadata": document["metadata"]}
