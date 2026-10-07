"""Regression coverage for source MVT buffers overlapping adjacent parcels."""

import json

import mapbox_vector_tile
import mercantile
import pytest
from shapely.geometry import box, mapping, shape

from src.pipelines.parcels_hcmc.transform import decode_tile


def write_tile(root, x, features):
    path = root / "16" / str(x) / "30790.pbf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        mapbox_vector_tile.encode(
            {"name": "alameda", "features": features},
            default_options={"y_coord_down": True, "extents": 4096},
        )
    )
    return path


def feature(geometry, identifier="parcel-1"):
    return {
        "geometry": mapping(geometry),
        "properties": {"UNIQ_ID": identifier, "MDSDD": "OTC"},
    }


def test_buffer_only_parcels_are_not_loaded_from_neighbor_tile(tmp_path):
    # Real source tiles include polygons down to -80 and up to 4176.
    path = write_tile(tmp_path, 52192, [feature(box(-80, 100, -10, 200))])

    assert decode_tile(path) == []


def test_parcel_crossing_source_boundary_is_clipped_to_its_tile(tmp_path):
    path = write_tile(tmp_path, 52192, [feature(box(-80, 100, 80, 200))])

    parcels = decode_tile(path)

    assert len(parcels) == 1
    parcel = shape(json.loads(parcels[0].geojson))
    bounds = mercantile.bounds(52192, 30790, 16)
    assert parcel.bounds[0] == pytest.approx(bounds.west, abs=1e-6)
    assert parcel.area > 0
    assert parcels[0].uniq_id == "parcel-1"


def test_adjacent_source_tiles_do_not_duplicate_buffer_area(tmp_path):
    # Both source tiles contain the same polygon within their 80-unit buffer.
    left = write_tile(tmp_path, 52191, [feature(box(4016, 100, 4176, 200))])
    right = write_tile(tmp_path, 52192, [feature(box(-80, 100, 80, 200))])

    left_geometry = shape(json.loads(decode_tile(left)[0].geojson))
    right_geometry = shape(json.loads(decode_tile(right)[0].geojson))

    assert left_geometry.intersection(right_geometry).area == pytest.approx(0, abs=1e-15)
    assert left_geometry.union(right_geometry).area > 0


def test_tile_boundary_touch_without_area_is_not_loaded_as_polygon(tmp_path):
    path = write_tile(tmp_path, 52192, [feature(box(-80, 100, 0, 200))])

    assert decode_tile(path) == []
