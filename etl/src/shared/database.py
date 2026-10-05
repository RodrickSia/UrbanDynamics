"""Shared PostGIS connection and atomic vector-layer publishing."""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg import Connection
from shapely.geometry import shape

from .data_io import data_dir, write_json


@dataclass(frozen=True)
class WarehouseConfig:
    """PostgreSQL connection settings loaded from WAREHOUSE_* environment vars."""

    host: str = "localhost"
    port: int = 5432
    database: str = "urbandynamics"
    user: str = "urbandynamics"
    password: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "WarehouseConfig":
        """Create settings from the environment, using local-development defaults."""
        return cls(
            host=os.getenv("WAREHOUSE_HOST") or "localhost",
            port=int(os.getenv("WAREHOUSE_PORT") or "5432"),
            database=os.getenv("WAREHOUSE_DATABASE") or "urbandynamics",
            user=os.getenv("WAREHOUSE_USER") or "urbandynamics",
            password=os.getenv("WAREHOUSE_PASSWORD") or "",
        )

    def connect(self) -> Connection:
        """Open a synchronous psycopg connection to the warehouse."""
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )


def connect_to_warehouse() -> Connection:
    """Open a warehouse connection using the current environment settings."""
    return WarehouseConfig.from_env().connect()


def warehouse_configured() -> bool:
    """Use PostGIS when a password is configured; otherwise use local snapshots."""
    return bool(os.getenv("WAREHOUSE_PASSWORD", "").strip())


def _validate_document(layer: str, document: dict[str, Any]) -> list[tuple[str, dict, dict, str | None]]:
    if re.fullmatch(r"[a-z][a-z0-9_]*", layer) is None:
        raise ValueError("Layer name must contain lowercase letters, digits, and underscores")
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError("Layer data must be a GeoJSON FeatureCollection")
    metadata = document.get("metadata")
    features = document.get("features")
    if not isinstance(metadata, dict) or not isinstance(features, list):
        raise ValueError("FeatureCollection requires metadata and a feature list")

    normalized = []
    seen: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Feature {index} is not a GeoJSON Feature")
        raw_id = feature.get("id")
        if raw_id is None or isinstance(raw_id, (dict, list, bool)):
            raise ValueError(f"Feature {index} requires a scalar id")
        feature_id = str(raw_id)
        if not feature_id or feature_id in seen:
            raise ValueError(f"Duplicate or empty feature id: {feature_id!r}")
        seen.add(feature_id)
        properties = feature.get("properties", {})
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ValueError(f"Feature {feature_id!r} requires geometry and object properties")
        try:
            parsed_geometry = shape(geometry)
        except Exception as error:
            raise ValueError(f"Invalid geometry for feature {feature_id!r}") from error
        if parsed_geometry.is_empty or not parsed_geometry.is_valid:
            raise ValueError(f"Empty or invalid geometry for feature {feature_id!r}")
        west, south, east, north = parsed_geometry.bounds
        if west < -180 or east > 180 or south < -90 or north > 90:
            raise ValueError(f"Geometry for feature {feature_id!r} is outside WGS84 coordinate bounds")
        try:
            json.dumps(properties, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Properties for feature {feature_id!r} are not valid JSON") from error
        observed_at = properties.get("observed_at")
        if observed_at is not None and not isinstance(observed_at, str):
            raise ValueError(f"observed_at for feature {feature_id!r} must be an ISO timestamp string")
        normalized.append((feature_id, geometry, properties, observed_at))
    json.dumps(metadata, allow_nan=False)
    return normalized


def publish(layer: str, document: dict[str, Any], root: str | Path | None = None) -> dict[str, Any]:
    """Atomically replace a layer snapshot in PostGIS or a local GeoJSON file."""
    if not isinstance(layer, str) or not layer.strip():
        raise ValueError("Layer name must be non-empty")
    rows = _validate_document(layer, document)
    metadata = dict(document["metadata"])
    metadata["layer"] = layer
    normalized_document = {"type": "FeatureCollection", "features": document["features"], "metadata": metadata}

    if not warehouse_configured():
        target = Path(root) if root is not None else data_dir()
        write_json(target / "layers" / f"{layer}.geojson", normalized_document)
        return {"layer": layer, "features": len(rows), "storage": "snapshot"}

    with connect_to_warehouse() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (layer,))
        connection.execute(
            """INSERT INTO layer_snapshots (layer, metadata, updated_at)
               VALUES (%s, %s, now())
               ON CONFLICT (layer) DO UPDATE SET metadata = EXCLUDED.metadata, updated_at = now()""",
            (layer, Jsonb(metadata)),
        )
        connection.execute("DELETE FROM layer_features WHERE layer = %s", (layer,))
        for feature_id, geometry, properties, observed_at in rows:
            connection.execute(
                """INSERT INTO layer_features (layer, feature_id, geom, properties, observed_at)
                   VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s::timestamptz)""",
                (layer, feature_id, json.dumps(geometry, allow_nan=False), Jsonb(properties), observed_at),
            )
    return {"layer": layer, "features": len(rows), "storage": "postgis"}


def read_layer_document(layer: str, root: str | Path | None = None) -> dict[str, Any]:
    """Read a complete layer snapshot from PostGIS or the local snapshot directory."""
    if not warehouse_configured():
        path = (Path(root) if root is not None else data_dir()) / "layers" / f"{layer}.geojson"
        if not path.is_file():
            raise FileNotFoundError(f"No snapshot exists for layer {layer!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    with connect_to_warehouse() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        snapshot = connection.execute(
            "SELECT metadata FROM layer_snapshots WHERE layer = %s", (layer,)
        ).fetchone()
        if snapshot is None:
            raise FileNotFoundError(f"No snapshot exists for layer {layer!r}")
        rows = connection.execute(
            """SELECT feature_id, ST_AsGeoJSON(geom), properties
               FROM layer_features WHERE layer = %s ORDER BY feature_id""",
            (layer,),
        ).fetchall()
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "id": feature_id, "geometry": json.loads(geometry), "properties": properties}
            for feature_id, geometry, properties in rows
        ],
        "metadata": snapshot[0],
    }
