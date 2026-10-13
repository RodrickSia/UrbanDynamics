"""Read-only team API + OSM snapshot acquisition for a bounded local pilot.

Example: python scripts/prepare-simulation-background.py --ssh-host 192.168.20.156
No server files, containers, database or deployment are changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from urllib.parse import urlencode

import requests
from shapely.geometry import mapping
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"backend"), str(ROOT/"etl")]
from app.routers.integrated_scenarios import demo_payload
from app.services.simulation.engine import polygon_and_area
from app.services.simulation.models import PolygonInput
from app.services.simulation.integrated.background import publish, canonical
from app.services.simulation.integrated.context import projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", help="SSH config host; reads localhost API remotely without copying credentials")
    parser.add_argument("--backend-container", help="With --ssh-host, read the API inside this existing backend container")
    parser.add_argument("--base-url", default="http://127.0.0.1:51873")
    parser.add_argument("--site-file", help="GeoJSON Polygon or Feature; default is Thu Duc apartment demo")
    parser.add_argument("--radius-m", type=int, default=1000)
    parser.add_argument("--output-dir", default=str(ROOT/"data"/"simulation_snapshots"))
    parser.add_argument("--without-osm", action="store_true")
    parser.add_argument("--without-landcover", action="store_true")
    args = parser.parse_args()
    if not 500 <= args.radius_m <= 1500:
        parser.error("radius-m must be between 500 and 1500 for this pilot")
    site_raw = json.loads(Path(args.site_file).read_text(encoding="utf-8")) if args.site_file else demo_payload()["site"]
    if site_raw.get("type") == "Feature":
        site_raw = site_raw["geometry"]
    site, area = polygon_and_area(PolygonInput(**site_raw))
    if area > 100000:
        parser.error("Pilot site must not exceed 100,000 m2")
    forward, backward = projection(site)
    bbox = list(transform(backward, transform(forward, site).buffer(args.radius_m)).bounds)
    sources, failures = {}, {}
    def get(path):
        url = args.base_url.rstrip("/")+path
        if args.ssh_host:
            if args.ssh_host.startswith("-"):
                parser.error("Invalid SSH host")
            if args.backend_container:
                code = "import urllib.request,sys;sys.stdout.buffer.write(urllib.request.urlopen("+repr(url)+",timeout=30).read(30000001))"
                command = "docker exec "+shlex.quote(args.backend_container)+" python -c "+shlex.quote(code)
            else:
                command = "curl -fsS --max-time 30 "+shlex.quote(url)
            output = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", args.ssh_host,
                                     command], check=True, capture_output=True, timeout=40)
            raw = output.stdout
        else:
            response = requests.get(url, timeout=(8, 30))
            response.raise_for_status()
            raw = response.content
        if len(raw) > 30_000_000:
            raise ValueError("API response exceeds bounded pilot snapshot size")
        sources[path.split("?")[0]] = {"url": url, "transport": "ssh_read_only" if args.ssh_host else "http",
                                       "sha256": hashlib.sha256(raw).hexdigest()}
        return json.loads(raw)
    snapshot = {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(), "bbox": bbox,
                "site": mapping(site), "radius_m": args.radius_m, "sources": sources, "failures": failures, "layers": {}}
    catalog = get("/api/v1/layers")
    snapshot["catalog"] = catalog
    print("Team layer catalog read", flush=True)
    bbox_query = urlencode({"bbox": ",".join(str(x) for x in bbox), "limit": 10000})
    for layer in ("parcels", "flood_history", "flood_risk", "land_price"):
        if not any(x["id"] == layer and x["available"] for x in catalog["layers"]):
            failures[layer] = "Unavailable in team catalog"
            continue
        document = get(f"/api/v1/layers/{layer}/features?{bbox_query}")
        if layer == "parcels":
            snapshot[layer] = document
        else:
            snapshot["layers"][layer] = document
        print(f"{layer}: {len(document.get('features', []))} features", flush=True)
    population = get("/api/v1/population")
    eligible_years = [y for y in population.get("years", []) if y["year"] <= datetime.now(timezone.utc).year]
    if eligible_years:
        year = max(eligible_years, key=lambda y: y["year"])
        snapshot["population"] = get(f"/api/v1/population/{year['year']}/stats?"+urlencode({"bbox": ",".join(str(x) for x in bbox)}))
        snapshot["population"].update(source=year, kind="worldpop_estimate")
        print(f"Population {year['year']}: {snapshot['population']['statistics']['population_sum']:.1f} people in bbox", flush=True)
    else:
        failures["population"] = "No non-future population raster year loaded"
    if not args.without_osm:
        west, south, east, north = bbox
        bounds = f"({south},{west},{north},{east})"
        query = f'[out:json][timeout:45];(way["highway"]{bounds};way["building"]{bounds};way["landuse"]{bounds};way["leisure"~"park|garden"]{bounds};nwr["amenity"~"school|kindergarten|college|university|hospital|clinic"]{bounds};node["highway"="traffic_signals"]{bounds};);out body geom;'
        client = requests.Session()
        client.headers["User-Agent"] = "UrbanDynamics/0.1 (+https://github.com/RodrickSia/UrbanDynamics; research pilot)"
        for endpoint in ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"):
            try:
                response = client.post(endpoint, data={"data": query}, timeout=(15, 55))
                response.raise_for_status()
                document = response.json()
                if document.get("remark") or "elements" not in document or len(document["elements"]) > 12000:
                    raise ValueError("Incomplete or oversized OSM extract")
                snapshot["osm"] = document
                sources["osm"] = {"url": endpoint, "query": query, "license": "ODbL-1.0", "attribution": "OpenStreetMap contributors",
                                  "sha256": hashlib.sha256(canonical(document)).hexdigest(), "osm_base_timestamp": document.get("osm3s", {}).get("timestamp_osm_base")}
                print(f"OSM: {len(document['elements'])} elements", flush=True)
                break
            except (requests.RequestException, ValueError) as error:
                failures[endpoint] = type(error).__name__
                print(f"OSM source failed: {type(error).__name__}", flush=True)
        if "osm" not in snapshot:
            raise RuntimeError("No OSM snapshot published; run again or explicitly use --without-osm")
    if not args.without_landcover:
        from app.services.simulation.integrated.landcover import fetch
        try:
            snapshot["landcover"] = fetch(bbox)
            sources["landcover"] = snapshot["landcover"]["metadata"]
            print(f"Land cover: {len(snapshot['landcover']['features'])} polygons", flush=True)
        except Exception as error:
            failures["landcover"] = type(error).__name__
            print(f"Land cover unavailable: {type(error).__name__}; OSM/assumptions remain explicit", flush=True)
    identifier = publish(snapshot, args.output_dir)
    print(json.dumps({"snapshot_id": identifier, "directory": args.output_dir, "bbox": bbox, "failures": failures}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
