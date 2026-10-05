"""Fetch OSM roads and export unapproved full-road candidates for manual segment review."""
import sys
import argparse
import requests
from pathlib import Path
from shapely.geometry import LineString, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"etl"))
from src.shared.data_io import data_dir, read_json, write_json, session
from src.pipelines.flood_history.transform import normalize

def run(cached=False):
    endpoint = "https://overpass-api.de/api/interpreter"
    query = '[out:json][timeout:60];way["highway"]["name"](10.74,106.70,10.84,106.81);out geom;'
    cache = data_dir()/"raw"/"land_price"/"osm_roads.json"
    if cached:
        data = read_json(cache)
    else:
        try:
            response = session().get(endpoint, params={"data": query}, timeout=(20,90))
            response.raise_for_status()
        except requests.RequestException:
            endpoint = "https://overpass.private.coffee/api/interpreter"
            response = session().get(endpoint, params={"data": query}, timeout=(20,90))
            response.raise_for_status()
        data = response.json()
        data["source_endpoint"] = endpoint
        write_json(cache, data)
    endpoint = data.get("source_endpoint", "https://overpass.private.coffee/api/interpreter")
    rows = read_json(data_dir()/"review"/"land_price_rows.json")["records"]
    roads = []
    for way in data["elements"]:
        coordinates = [(p["lon"],p["lat"]) for p in way.get("geometry",[])]
        if len(coordinates) >= 2:
            roads.append((way, LineString(coordinates)))
    output = []
    for row in rows:
        # Remove the ward suffix, retain road identity. Ambiguous names stay unapproved.
        wanted = normalize(row["road"].split(",")[0])
        candidates = [(way,geom) for way,geom in roads if normalize(way["tags"]["name"]) in
                      (wanted, wanted.removeprefix("duong"))]
        if candidates:
            output.append({"type":"Feature", "id":row["id"],
                           "geometry":mapping(unary_union([g for _,g in candidates])),
                           "properties":{"price_record_id":row["id"], "road":row["road"],
                               "from":row["from"], "to":row["to"], "reviewed":False,
                               "price_values_reviewed":False, "osm_way_ids":[w["id"] for w,_ in candidates],
                               "geometry_source_url":endpoint, "geometry_license":"ODbL 1.0",
                               "review_note":"Full named road candidate; clip to published from/to intersections before approval"}})
    path = data_dir()/"review"/"land_price_candidates.geojson"
    write_json(path,{"type":"FeatureCollection","features":output,
                     "metadata":{"source_url":endpoint,"query":query,"source_time":data.get("osm3s",{}).get("timestamp_osm_base")}})
    print("OSM ways:",len(roads),"unapproved candidates:",len(output),"file:",path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached",action="store_true",help="Regenerate candidates using the existing OSM download")
    run(parser.parse_args().cached)
