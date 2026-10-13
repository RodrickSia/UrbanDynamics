import json

import shapely
from pyproj import Transformer
from shapely.geometry import box, mapping
from src.pipelines.buildings_footprint_gba.config import GBABuildingsConfig
from src.pipelines.buildings_footprint_gba.transform import run


def test_transform_joins_height_and_clips_to_hcmc_boundary(tmp_path):
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    inside = shapely.transform(
        box(106.70, 10.70, 106.71, 10.71), to_mercator.transform, interleaved=False
    )
    inside_duplicate_key = shapely.transform(
        box(106.72, 10.70, 106.73, 10.71), to_mercator.transform, interleaved=False
    )
    outside = shapely.transform(
        box(105.0, 10.70, 105.01, 10.71), to_mercator.transform, interleaved=False
    )
    polygon_path = tmp_path / "polygons.geojson"
    polygon_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"source": "osm", "id": 12, "region": "asiawest"},
                        "geometry": mapping(inside),
                    },
                    {
                        "type": "Feature",
                        "properties": {"source": "osm", "id": 12, "region": "asiawest"},
                        "geometry": mapping(inside_duplicate_key),
                    },
                    {
                        "type": "Feature",
                        "properties": {"source": "osm", "id": 13, "region": "asiawest"},
                        "geometry": mapping(outside),
                    },
                ],
            }
        )
    )
    heights_path = tmp_path / "heights.json"
    heights_path.write_text(
        json.dumps(
            {
                "osm12asiawest": {"height": 13.25, "var": -1},
                "osm13asiawest": {"height": 8.0, "var": 1.0},
            }
        )
    )
    boundary_path = tmp_path / "boundary.geojson"
    boundary_path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "geometry": mapping(box(106.6, 10.6, 106.8, 10.8)),
                "properties": {},
            }
        )
    )
    output_path = tmp_path / "normalized.geojson"
    settings = GBABuildingsConfig(
        boundary_path=boundary_path,
        polygon_path=polygon_path,
        heights_path=heights_path,
        normalized_path=output_path,
        height_index_path=tmp_path / "work" / "heights.sqlite3",
    )

    result = run(settings=settings)
    document = json.loads(result.read_text())

    assert len(document["features"]) == 2
    feature, duplicate = document["features"]
    assert feature["properties"]["feature_id"].startswith("osm12asiawest:")
    assert duplicate["properties"]["gba_id"] == feature["properties"]["gba_id"]
    assert duplicate["properties"]["feature_id"] != feature["properties"]["feature_id"]
    assert feature["properties"]["gba_id"] == "osm12asiawest"
    assert feature["properties"]["height_m"] == 13.25
    assert feature["properties"]["height_variance"] is None
    assert feature["geometry"]["type"] == "MultiPolygon"
