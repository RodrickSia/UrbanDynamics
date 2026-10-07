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

def run(cached=False,boundary=None):
    endpoint = "https://overpass-api.de/api/interpreter"
    query = '[out:json][timeout:60];way["highway"]["name"](10.74,106.70,10.84,106.81);out geom;'
    cache = data_dir()/"raw"/"land_price"/"osm_roads.json"
    if cached:
        data = read_json(cache)
    else:
        from src.pipelines.rainwater.config import Settings
        from src.pipelines.rainwater.grid import build
        from src.shared.spatial import read_boundary
        boundary = Path(boundary or data_dir()/'inputs/hcmc_expanded_boundary.geojson')
        polygon = read_boundary(boundary)
        cells,grid = build(Settings(boundary,grid_m=50000))
        elements,queries = {},[]
        for index,cell in enumerate(cells):
            west,south,east,north = __import__('shapely').geometry.shape(cell['geometry']).bounds
            query = f'[out:json][timeout:90];way["highway"]["name"]({south},{west},{north},{east});out geom;'
            chunk = data_dir()/f'raw/land_price/osm_chunks/{grid["grid_id"]}-{index}.json'
            if chunk.exists():
                part = read_json(chunk)
            else:
                try:
                    response = session().get(endpoint,params={'data':query},timeout=(20,120)); response.raise_for_status()
                except requests.RequestException:
                    endpoint = 'https://overpass.private.coffee/api/interpreter'
                    response = session().get(endpoint,params={'data':query},timeout=(20,120)); response.raise_for_status()
                part = response.json(); write_json(chunk,part)
            for way in part['elements']:
                coords = [(p['lon'],p['lat']) for p in way.get('geometry',[])]
                if len(coords)>=2 and LineString(coords).intersects(polygon): elements[way['id']]=way
            queries.append(query)
            print('OSM chunk',index+1,'/',len(cells),'ways',len(elements),flush=True)
        data = {'elements':list(elements.values()),'source_endpoint':endpoint,
                'queries':queries,'scope':'HCMC expanded','osm3s':part.get('osm3s',{})}
        write_json(cache, data)
    endpoint = data.get("source_endpoint", "https://overpass.private.coffee/api/interpreter")
    rows = read_json(data_dir()/"review"/"land_price_rows.json")["records"]
    roads = []
    for way in data["elements"]:
        coordinates = [(p["lon"],p["lat"]) for p in way.get("geometry",[])]
        if len(coordinates) >= 2:
            roads.append((way, LineString(coordinates)))
    output = []
    by_name,merged = {},{}
    for way,geometry in roads:
        by_name.setdefault(normalize(way['tags']['name']),[]).append((way,geometry))
    for row in rows:
        # Remove the ward suffix, retain road identity. Ambiguous names stay unapproved.
        wanted = normalize(row["road"].split(",")[0])
        if wanted not in merged:
            candidates = [item for key in {wanted,wanted.removeprefix('duong')}
                          for item in by_name.get(key,[])]
            merged[wanted] = (candidates,mapping(unary_union([g for _,g in candidates])) if candidates else None)
        candidates,geometry = merged[wanted]
        if candidates:
            output.append({"type":"Feature", "id":row["id"],
                           "geometry":geometry,
                           "properties":{"price_record_id":row["id"], "road":row["road"],
                               "from":row["from"], "to":row["to"], 'ward':row.get('ward'),
                               'region_id':row.get('region_id'), "reviewed":False,
                               "price_values_reviewed":False, "osm_way_ids":[w["id"] for w,_ in candidates],
                               "geometry_source_url":endpoint, "geometry_license":"ODbL 1.0",
                               "review_note":"Full named road candidate; clip to published from/to intersections before approval"}})
    path = data_dir()/"review"/"land_price_candidates.geojson"
    write_json(path,{"type":"FeatureCollection","features":output,
                     'metadata':{'source_url':endpoint,'queries':data.get('queries',[query]),
                                 'scope':data.get('scope','Cached source coverage'),
                                 'source_time':data.get('osm3s',{}).get('timestamp_osm_base')}})
    print("OSM ways:",len(roads),"unapproved candidates:",len(output),"file:",path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached",action="store_true",help="Regenerate candidates using the existing OSM download")
    parser.add_argument('--boundary',help='Citywide WGS84 GeoJSON boundary')
    args = parser.parse_args()
    run(args.cached,args.boundary)
