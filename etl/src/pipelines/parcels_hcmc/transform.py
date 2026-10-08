"""Decode a land-plot vector tile into WGS84 polygons."""

import json
import math
from pathlib import Path

import mapbox_vector_tile
import mercantile
from mapbox_vector_tile.Mapbox import vector_tile_pb2 as vector_tile
from shapely.geometry import box, mapping, shape
from shapely import make_valid

from src.pipelines.parcels_hcmc.models import LandPlot

_POLYGON_TYPES = {"Polygon", "MultiPolygon"}
_DROPPED_KEY_PARTS = ("price", "gia", "avg_price")


def _text(properties: dict, key: str) -> str | None:
    value = properties.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in ('', 'null', 'none', 'nan') else text


def _to_wgs84(geometry: dict, z: int, x: int, y: int, extent: int) -> dict:
    bounds = mercantile.bounds(x, y, z)
    sx = (bounds.east - bounds.west) / extent

    def convert(coordinates):
        if isinstance(coordinates[0], (int, float)):
            longitude = bounds.west + coordinates[0] * sx
            world_y = (y + coordinates[1] / extent) / 2**z
            latitude = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * world_y))))
            return [round(longitude, 9), round(latitude, 9)]
        return [convert(part) for part in coordinates]

    return {"type": geometry["type"], "coordinates": convert(geometry["coordinates"])}


def _layer_extent(raw: bytes, name: str) -> int:
    tile = vector_tile.tile()
    tile.ParseFromString(raw)
    for layer in tile.layers:
        if layer.name == name and layer.extent:
            return layer.extent
    return 4096


def decode_tile(path: Path) -> list[LandPlot]:
    """Return plot polygons stored in one ``.pbf`` tile."""
    raw = path.read_bytes()
    if not raw:
        return []
    tile_z = int(path.parent.parent.name)
    tile_x = int(path.parent.name)
    tile_y = int(path.stem)

    # MVT coordinates use a top-left origin. Keep the source y direction so
    # the tile-to-WGS84 conversion below can measure down from tile.north.
    decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})
    plots: list[LandPlot] = []
    for layer_name, layer in decoded.items():
        extent = _layer_extent(raw, layer_name)
        for feature in layer["features"]:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in _POLYGON_TYPES:
                continue
            clipped = make_valid(shape(geometry)).intersection(box(0, 0, extent, extent))
            if clipped.is_empty or clipped.area == 0:
                continue
            if clipped.geom_type == 'GeometryCollection':
                from shapely.ops import unary_union
                clipped = unary_union([part for part in clipped.geoms if part.geom_type in _POLYGON_TYPES])
            geometry = mapping(clipped)
            properties = {
                key: value
                for key, value in (feature.get("properties") or {}).items()
                if not any(part in key.lower() for part in _DROPPED_KEY_PARTS)
            }
            plots.append(
                LandPlot(
                    uniq_id=_text(properties, "UNIQ_ID"),
                    tinh=_text(properties, "Tinh"),
                    quan=_text(properties, "Quan"),
                    phuong=_text(properties, "Phuong"),
                    to_ban_do=_text(properties, "to_ban_do_so_moi"),
                    thua=_text(properties, "thua_dat_so_moi"),
                    mdsdd=_text(properties, "MDSDD"),
                    loai_dat_qh=_text(properties, "LoaiDatQH"),
                    quyet_dinh=_text(properties, "QuyetDinh"),
                    do_an=_text(properties, "DoAn"),
                    tile_z=tile_z,
                    tile_x=tile_x,
                    tile_y=tile_y,
                    geojson=json.dumps(_to_wgs84(geometry, tile_z, tile_x, tile_y, extent)),
                )
            )
    return plots


def run(download_dir: Path) -> Path:
    """Validate the extracted tile tree before the streaming PostGIS load."""
    if not download_dir.is_dir():
        raise FileNotFoundError(f"Parcel download directory does not exist: {download_dir}")
    tiles = sorted(download_dir.glob("*/*/*.pbf"))
    if not tiles:
        raise FileNotFoundError(f"No parcel tiles found under {download_dir}")
    for path in tiles:
        try:
            z, x, y = int(path.parent.parent.name), int(path.parent.name), int(path.stem)
        except ValueError as error:
            raise ValueError(f"Invalid parcel tile path: {path}") from error
        if z < 0 or not 0 <= x < 2**z or not 0 <= y < 2**z:
            raise ValueError(f"Invalid XYZ parcel tile coordinates: {path}")
    return download_dir
