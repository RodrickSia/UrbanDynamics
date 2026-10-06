"""Match published land-price rows to named OSM roads for automatic publication."""

import argparse
import sys
from pathlib import Path

import requests
from shapely.geometry import LineString, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
ETL_SOURCE = ROOT / "etl"
if not ETL_SOURCE.is_dir():
    ETL_SOURCE = ROOT
sys.path.insert(0, str(ETL_SOURCE))
from src.pipelines.flood_history.transform import normalize
from src.shared.data_io import data_dir, read_json, session, write_json


def run(cached=False):
    endpoint = "https://overpass-api.de/api/interpreter"
    query = '[out:json][timeout:60];way["highway"]["name"](10.74,106.70,10.84,106.81);out geom;'
    cache = data_dir() / "raw" / "land_price" / "osm_roads.json"
    if cached:
        data = read_json(cache)
    else:
        try:
            response = session().get(endpoint, params={"data": query}, timeout=(20, 90))
            response.raise_for_status()
        except requests.RequestException:
            endpoint = "https://overpass.private.coffee/api/interpreter"
            response = session().get(endpoint, params={"data": query}, timeout=(20, 90))
            response.raise_for_status()
        data = response.json()
        data["source_endpoint"] = endpoint
        write_json(cache, data)
    endpoint = data.get(
        "source_endpoint", "https://overpass.private.coffee/api/interpreter"
    )
    rows = read_json(data_dir() / "review" / "land_price_rows.json")["records"]
    roads = []
    for way in data["elements"]:
        coordinates = [(p["lon"], p["lat"]) for p in way.get("geometry", [])]
        if len(coordinates) >= 2:
            roads.append((way, LineString(coordinates)))
    output = []
    for row in rows:
        # Remove the ward suffix and match by normalized road name.
        wanted = normalize(row["road"].split(",")[0])
        candidates = [
            (way, geom)
            for way, geom in roads
            if normalize(way["tags"]["name"]) in (wanted, wanted.removeprefix("duong"))
        ]
        if candidates:
            output.append(
                {
                    "type": "Feature",
                    "id": row["id"],
                    "geometry": mapping(unary_union([g for _, g in candidates])),
                    "properties": {
                        "price_record_id": row["id"],
                        "road": row["road"],
                        "from": row["from"],
                        "to": row["to"],
                        "auto_approved": True,
                        "match_method": "exact_normalized_osm_name",
                        "geometry_coverage": "whole_named_road_proxy",
                        "osm_way_ids": [w["id"] for w, _ in candidates],
                        "geometry_source_url": endpoint,
                        "geometry_license": "ODbL 1.0",
                        "review_note": (
                            "Automatically matched by normalized road name. Geometry covers the full named road; "
                            "the published from/to endpoints are attributes and were not used to clip geometry."
                        ),
                    },
                }
            )
    path = data_dir() / "review" / "land_price_auto_segments.geojson"
    write_json(
        path,
        {
            "type": "FeatureCollection",
            "features": output,
            "metadata": {
                "source_url": endpoint,
                "query": query,
                "matching_method": "exact_normalized_osm_name",
                "geometry_coverage": "whole_named_road_proxy",
                "source_time": data.get("osm3s", {}).get("timestamp_osm_base"),
            },
        },
    )
    print("OSM ways:", len(roads), "automatically matched rows:", len(output), "file:", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Regenerate automatic matches using the existing OSM download",
    )
    run(parser.parse_args().cached)
