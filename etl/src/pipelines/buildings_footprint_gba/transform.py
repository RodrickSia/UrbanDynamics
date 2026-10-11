"""Join GBA height estimates and clip tile geometry to the HCMC boundary."""

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import ijson
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import unary_union

from src.pipelines.buildings_footprint_gba.config import GBABuildingsConfig, config

logger = logging.getLogger(__name__)
WEB_MERCATOR_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
WGS84_TO_WEB_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def _load_boundary(path: Path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") == "FeatureCollection":
        geometries = [shape(item["geometry"]) for item in document.get("features", [])]
    elif document.get("type") == "Feature":
        geometries = [shape(document["geometry"])]
    else:
        geometries = [shape(document)]
    geometries = [geometry for geometry in geometries if not geometry.is_empty]
    if not geometries:
        raise ValueError(f"HCMC boundary has no geometry: {path}")
    boundary = unary_union(geometries)
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    if boundary.geom_type not in ("Polygon", "MultiPolygon") or boundary.is_empty:
        raise ValueError(f"HCMC boundary must be a valid polygon: {path}")
    return boundary


def _feature_key(properties: dict[str, Any]) -> str:
    try:
        return "".join(str(properties[name]) for name in ("source", "id", "region"))
    except KeyError as error:
        raise ValueError(f"GBA feature missing key field {error.args[0]!r}") from error


def _coordinate_bounds(coordinates: list) -> tuple[float, float, float, float] | None:
    """Find GeoJSON coordinate bounds without constructing a GEOS geometry."""
    west = south = float("inf")
    east = north = float("-inf")
    stack = [coordinates]
    found = False
    while stack:
        item = stack.pop()
        if not item:
            continue
        if isinstance(item[0], (int, float)):
            x, y = item[:2]
            west = min(west, x)
            east = max(east, x)
            south = min(south, y)
            north = max(north, y)
            found = True
        else:
            stack.extend(item)
    return (west, south, east, north) if found else None


def _build_height_index(source: Path, index_path: Path) -> int:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.is_file() and index_path.stat().st_size:
        try:
            with sqlite3.connect(index_path) as cached:
                rows = cached.execute("SELECT count(*) FROM heights").fetchone()[0]
            if rows:
                logger.info(
                    "Using cached height index with %s records: %s", rows, index_path
                )
                return rows
        except sqlite3.Error:
            logger.warning("Removing incomplete GBA height index: %s", index_path)
            index_path.unlink(missing_ok=True)

    temporary_index = index_path.with_suffix(index_path.suffix + ".part")
    temporary_index.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_index)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute(
            "CREATE TABLE heights (gba_id TEXT PRIMARY KEY, height REAL, variance REAL) WITHOUT ROWID"
        )
        inserted = 0
        with source.open("rb") as document:
            batch = []
            for key, value in ijson.kvitems(document, "", use_float=True):
                height = value.get("height")
                variance = value.get("var")
                batch.append(
                    (
                        key,
                        None if height == -999 else height,
                        None if variance == -999 else variance,
                    )
                )
                if len(batch) >= 10000:
                    connection.executemany(
                        "INSERT OR REPLACE INTO heights VALUES (?, ?, ?)", batch
                    )
                    inserted += len(batch)
                    batch.clear()
                    if inserted % 500000 == 0:
                        logger.info("Indexed %s GBA height records", inserted)
            if batch:
                connection.executemany(
                    "INSERT OR REPLACE INTO heights VALUES (?, ?, ?)", batch
                )
                inserted += len(batch)
        connection.commit()
    finally:
        connection.close()
    temporary_index.replace(index_path)
    logger.info("Built height lookup with %s records at %s", inserted, index_path)
    return inserted


def run(
    source: str | Path | None = None,
    settings: GBABuildingsConfig = config,
) -> Path:
    """Stream the tile, clip to HCMC, and write a compact GeoJSON snapshot."""
    polygon_path = Path(source) if source else settings.polygon_path
    if not polygon_path.is_file() or not polygon_path.stat().st_size:
        raise FileNotFoundError(f"GBA polygon tile is missing: {polygon_path}")
    if not settings.heights_path.is_file() or not settings.heights_path.stat().st_size:
        raise FileNotFoundError(
            f"GBA LoD1 height file is missing: {settings.heights_path}"
        )
    if not settings.boundary_path.is_file():
        raise FileNotFoundError(f"HCMC boundary is missing: {settings.boundary_path}")

    destination = settings.normalized_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    boundary = _load_boundary(settings.boundary_path)
    boundary_mercator = shapely.transform(
        boundary, WGS84_TO_WEB_MERCATOR.transform, interleaved=False
    )
    boundary_west, boundary_south, boundary_east, boundary_north = (
        boundary_mercator.bounds
    )
    _build_height_index(settings.heights_path, settings.height_index_path)
    index = sqlite3.connect(settings.height_index_path)
    count = missing_heights = 0
    try:
        with (
            polygon_path.open("rb") as source_file,
            temporary.open("w", encoding="utf-8") as output,
        ):
            output.write('{"type":"FeatureCollection","features":[')
            for scanned, feature in enumerate(
                ijson.items(source_file, "features.item", use_float=True), start=1
            ):
                if scanned % 1_000_000 == 0:
                    logger.info(
                        "Scanned %s GBA polygons; retained %s for HCMC", scanned, count
                    )
                coordinates = (feature.get("geometry") or {}).get("coordinates")
                bounds = _coordinate_bounds(coordinates) if coordinates else None
                if bounds is None:
                    continue
                west, south, east, north = bounds
                if (
                    east < boundary_west
                    or west > boundary_east
                    or north < boundary_south
                    or south > boundary_north
                ):
                    continue
                properties = feature.get("properties") or {}
                geom = shape(feature["geometry"])
                if geom.is_empty:
                    continue
                geom = shapely.transform(
                    geom, WEB_MERCATOR_TO_WGS84.transform, interleaved=False
                )
                if not geom.is_valid:
                    geom = geom.buffer(0)
                if geom.is_empty or not geom.intersects(boundary):
                    continue
                clipped = geom.intersection(boundary)
                if not clipped.is_valid:
                    clipped = clipped.buffer(0)
                if clipped.is_empty:
                    continue
                if clipped.geom_type == "Polygon":
                    clipped = MultiPolygon([clipped])
                elif clipped.geom_type == "GeometryCollection":
                    polygons = [
                        part
                        for part in clipped.geoms
                        if part.geom_type == "Polygon" and not part.is_empty
                    ]
                    if not polygons:
                        continue
                    clipped = MultiPolygon(polygons)
                elif clipped.geom_type != "MultiPolygon":
                    continue
                key = _feature_key(properties)
                row = index.execute(
                    "SELECT height, variance FROM heights WHERE gba_id=?", (key,)
                ).fetchone()
                if not row or row[0] is None:
                    height_m = variance = None
                    missing_heights += 1
                else:
                    height_m, variance = row
                    if height_m < 0:
                        height_m = None
                        missing_heights += 1
                    if variance is not None and variance < 0:
                        variance = None
                row_feature = {
                    "type": "Feature",
                    "geometry": mapping(clipped),
                    "properties": {
                        "feature_id": f"{key}:{hashlib.sha256(clipped.wkb).hexdigest()}",
                        "gba_id": key,
                        "source": properties.get("source"),
                        "source_id": str(properties.get("id")),
                        "region": properties.get("region"),
                        "height_m": height_m,
                        "height_variance": variance,
                    },
                }
                if count:
                    output.write(",")
                json.dump(row_feature, output, separators=(",", ":"), allow_nan=False)
                count += 1
                if count % 50000 == 0:
                    output.flush()
                    logger.info("Clipped %s GBA buildings to HCMC", count)
            output.write("]}")
            output.flush()
    except Exception:
        temporary.unlink(missing_ok=True)
        logger.exception("GBA building transformation failed")
        raise
    finally:
        index.close()

    if count == 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("No GBA buildings intersect the HCMC boundary")
    temporary.replace(destination)
    settings.height_index_path.unlink(missing_ok=True)
    logger.info(
        "Wrote %s HCMC GBA buildings to %s; %s had missing height estimates",
        count,
        destination,
        missing_heights,
    )
    return destination
