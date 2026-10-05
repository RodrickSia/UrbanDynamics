"""Export a reviewed interior subset of the first Tran Nao price interval.

No new geometry is inferred. This subset does not cover the whole interval.
"""
import sys
from pathlib import Path
from shapely.geometry import MultiLineString, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"etl"))
from src.shared.data_io import data_dir, read_json, write_json

def run():
    rows = read_json(data_dir()/"review/land_price_rows.json")
    record = next(r for r in rows["records"] if r["road"] == "TRẦN NÃO"
                  and r["from"] == "XA LỘ HÀ NỘI" and r["to"] == "LƯƠNG ĐINH CỦA")
    actual = tuple(record[k] for k in ("residential_1000_vnd_m2", "commercial_1000_vnd_m2",
                                     "other_nonagricultural_1000_vnd_m2"))
    if actual != (152900,91700,76500) or record["pdf_page"] != 36:
        raise ValueError("Price row changed; repeat PDF review")
    source = read_json(data_dir()/"raw/land_price/osm_roads.json")
    ways = {w["id"]:w for w in source["elements"]}
    selected = [ways[i] for i in (242014077,691374898)]
    reviewed = read_json(ROOT/"docs/samples/land-price-tran-nao-reviewed.geojson")
    approved_coordinates = reviewed["features"][0]["geometry"]["coordinates"]
    lines = []
    for way in selected:
        if way["tags"]["name"] != "Trần Não":
            raise ValueError("OSM road identity changed; repeat review")
        coordinates = [(p["lon"],p["lat"]) for p in way["geometry"]]
        # Two reviewed carriageway subsets north of Luong Dinh Cua and south
        # of the former Xa Lo Ha Noi junction. Reject changed extents.
        if not all(106.728 < x < 106.733 and 10.78532 < y < 10.7956 for x,y in coordinates):
            raise ValueError("OSM geometry changed; repeat extent review")
        lines.append(coordinates)
    if mapping(MultiLineString(lines))["coordinates"] != tuple(tuple(tuple(p) for p in line) for line in approved_coordinates):
        raise ValueError("OSM coordinates differ from reviewed fixture; repeat review")
    properties = {"price_record_id":record["id"], "reviewed":True, "price_values_reviewed":True,
                  "geometry_coverage":"partial_published_segment", "osm_way_ids":[w["id"] for w in selected],
                  "geometry_source_url":"https://www.openstreetmap.org/way/242014077",
                  "geometry_license":"ODbL 1.0", "reviewed_at":"2026-10-04",
                  "review_note":"PDF page 36 (printed 37), first Tran Nao row: 152.900/91.700/76.500 thousand VND/m2. Two interior OSM carriageway subsets; coverage is partial."}
    result = {"type":"FeatureCollection", "features":[{"type":"Feature",
              "geometry":mapping(MultiLineString(lines)), "properties":properties}],
              "metadata":{"coverage":"one partial road segment", "source_time":source.get("osm3s",{}).get("timestamp_osm_base")}}
    target = data_dir()/"review/land_price_reviewed.geojson"
    if target.exists():
        existing = read_json(target)
        result["features"] += [f for f in existing["features"]
                              if f["properties"].get("price_record_id") != properties["price_record_id"]]
    write_json(target,result)
    print("Prepared one reviewed partial Tran Nao feature:",target)

if __name__ == "__main__":
    run()
