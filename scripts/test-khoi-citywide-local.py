"""Reproducible local integration run using a dedicated Docker/PostGIS stack.

Requires .venv dependencies and prepared real inputs. No server deployment.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests
from building_demo import sample_payload, prediction_payload, improvement_constraints

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-weather", action="store_true")
    parser.add_argument("--process-satellite", action="store_true")
    parser.add_argument("--road-candidates", action="store_true")
    parser.add_argument("--linux-checks", action="store_true", help="Also test Python 3.12 in Linux Docker")
    parser.add_argument('--api-only',action='store_true',help='Recheck API after a fix without rebuilding or rerunning pipelines/tests')
    args = parser.parse_args()
    environment = dict(os.environ)
    password = environment.get("POSTGRES_PASSWORD")
    if not password or not password.strip():
        raise SystemExit("Set POSTGRES_PASSWORD in your shell before running local tests; no default password is provided")
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if not docker or not Path(docker).exists():
        raise SystemExit("Docker not found; install Docker Desktop and start its engine")
    database_port = environment.get("KHOI_DB_PORT", "55432")
    api_port = environment.get("KHOI_API_PORT", "8001")
    environment["DATABASE_URL"] = f"postgresql://urban:{quote(password,safe='')}@127.0.0.1:{database_port}/urban"
    environment["TEST_DATABASE_URL"] = environment["DATABASE_URL"]
    environment["DATA_DIR"] = str(ROOT/"data")
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT/"etl"),str(ROOT/"backend")])
    output = ROOT/"test-results"
    output.mkdir(exist_ok=True)
    report = {"checked_at":datetime.now(timezone.utc).isoformat(), "steps":[], "api":{}}
    compose = [docker,"compose","-p","khoi-local","-f","compose.khoi.yaml"]

    def step(name, command):
        if args.api_only: return
        started = time.perf_counter()
        print("Running:",name,flush=True)
        with (output/f"{name}.log").open("w",encoding="utf-8") as log:
            completed = subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
        report["steps"].append({"name":name,"exit_code":completed.returncode,
                               "seconds":round(time.perf_counter()-started,3)})
        if completed.returncode:
            print((output/f"{name}.log").read_text(encoding="utf-8")[-2500:])
            raise RuntimeError(f"{name} failed; see test-results/{name}.log")

    def pipeline(name,*options):
        step(name,[sys.executable,"-m","src.main",name,*options])

    try:
        step("compose-build",[*compose,"up","-d","--build","warehouse","backend"])
        if not (ROOT/'data/inputs/hcmc_expanded_boundary.geojson').exists():
            step('prepare-boundary',[sys.executable,'scripts/prepare-hcmc-boundary.py','--cached'])
        if args.refresh_weather or not all((ROOT/"data/inputs"/name).exists()
                                           for name in ("rainwater_forecast.json","rainwater_history.json")):
            step('prepare-weather',[sys.executable,'-m','src.khoi_service','--once','--jobs','forecast','history'])
        source = ROOT/"data/raw/flood_history/HCMC_Floods_BDD.gpkg"
        pipeline("flood_history","--boundary","data/inputs/hcmc_expanded_boundary.geojson",
                 *(["--source",str(source)] if source.exists() else []))
        pipeline("flood_risk")
        source = ROOT/'data/review/land_price_rows.json'
        reviewed = ROOT/"data/review/land_price_reviewed.geojson"
        pipeline("land_price","--full-city",*(["--source",str(source)] if source.exists() else []),
                 *(["--segments",str(reviewed)] if reviewed.exists() else []))
        if args.road_candidates:
            step("road-candidates",[sys.executable,"scripts/prepare-land-road-review.py"])
        if args.process_satellite:
            pipeline('flood_satellite','--boundary','data/inputs/hcmc_expanded_boundary.geojson','--limit','100')
        elif not args.api_only:
            # Existing real satellite snapshots are also published to PostGIS.
            sys.path.insert(0,str(ROOT/"etl"))
            from src.shared.database import publish
            previous = dict(os.environ)
            os.environ.update(environment)
            try:
                for name in ("hcmc_boundary","hcmc_regions","rainwater","flood_satellite","flood_satellite_catalog"):
                    path = ROOT/"data/layers"/f"{name}.geojson"
                    if path.exists():
                        publish(name,json.loads(path.read_text(encoding="utf-8")))
            finally:
                os.environ.clear()
                os.environ.update(previous)
        step("pytest",[sys.executable,"-m","pytest","-q","--junitxml=test-results/khoi-local.xml"])
        if args.linux_checks:
            step("linux-test-build",[docker,"build","-f","infra/testing/Dockerfile","-t","khoi-local-tests","."])
            step("linux-pytest",[docker,"run","--rm","--network","khoi-local_default",
                 "-e",f"TEST_DATABASE_URL=postgresql://urban:{quote(password,safe='')}@warehouse:5432/urban",
                 "-v",f"{output}:/app/test-results","khoi-local-tests"])
            step("linux-land-price",[docker,"run","--rm","-e","PYTHONPATH=/app/etl",
                 "-e","DATA_DIR=/tmp/khoi-data","-v",f"{ROOT/'data'}:/inputs:ro",
                 "khoi-local-tests","python","-m","src.main","land_price",
                 '--source','/inputs/review/land_price_rows.json',
                 *(["--segments","/inputs/review/land_price_reviewed.geojson"] if reviewed.exists() else [])])
            # Validate all three service Dockerfiles, including the opt-in ETL.
            step("etl-build",[*compose,"build","etl"])
            step("frontend-build",[docker,"build","-t","khoi-local-frontend","frontend"])
        base = f"http://127.0.0.1:{api_port}"
        routes = {"health":"/health","ready":"/ready","layers":"/api/v1/layers",
                  "flood_history":"/api/v1/floods/history","flood_risk":"/api/v1/floods/risk",
                  "land_price":"/api/v1/land-prices","land_price_rows":"/api/v1/land-prices/rows"}
        if (ROOT/'data/layers/rainwater.geojson').exists():
            routes['rainwater'] = '/api/v1/weather/rain'
        satellite = ROOT/"data/layers/flood_satellite.geojson"
        if satellite.exists():
            routes["satellite"] = "/api/v1/floods/satellite"
        for name,route in routes.items():
            started = time.perf_counter()
            response = requests.get(base+route,timeout=15)
            response.raise_for_status()
            body = response.json()
            if name in ("flood_history","land_price"):
                assert body["metadata"]["provenance"], "Source checksum missing"
                assert all(len(p["sha256"]) == 64 for p in body["metadata"]["provenance"])
            report["api"][name] = {"http":response.status_code,"milliseconds":round((time.perf_counter()-started)*1000,1),
                                   "features":len(body["features"]) if "features" in body else None,
                                   "rows":len(body["records"]) if "records" in body else None}
        response = requests.post(base+"/api/v1/scenarios/rain",json={"rain_3h_mm":60},timeout=30)
        response.raise_for_status()
        report["api"]["rain_scenario"] = {"http":response.status_code,"features":len(response.json()["features"])}
        response = requests.get(base+"/simulation",timeout=15)
        response.raise_for_status()
        report["api"]["simulation_page"] = {"http":response.status_code}
        response = requests.post(base+"/api/v1/scenarios/building",json=sample_payload(),timeout=30)
        response.raise_for_status()
        scenario = response.json()
        reopened = requests.get(base+f"/api/v1/scenarios/building/{scenario['id']}",timeout=15)
        reopened.raise_for_status()
        assert reopened.json() == scenario, "Saved scenario differs from original run"
        assert scenario["variants"]["mitigated"]["unretained_runoff_m3"] < scenario["variants"]["development"]["unretained_runoff_m3"]
        report["api"]["building_scenario"] = {
            "http":response.status_code,"read_http":reopened.status_code,"id":scenario["id"],
            "site_area_m2":scenario["site_area_m2"],"input_sha256":scenario["input_sha256"],
            "unretained_runoff_m3":{key:round(value["unretained_runoff_m3"],3)
                                     for key,value in scenario["variants"].items()},
            "assessment_level":scenario["assessment_level"]}
        response = requests.post(base+"/api/v1/scenarios/building/predict",json=prediction_payload(),timeout=30)
        response.raise_for_status()
        prediction = response.json()
        assert "mitigated" not in prediction["inputs"], "Improved design must not be supplied as an input"
        response = requests.post(base+f"/api/v1/scenarios/building/{prediction['id']}/recommendations",
                                 json=improvement_constraints(prediction["site_area_m2"]),timeout=30)
        response.raise_for_status()
        recommended = response.json()
        assert recommended["recommendations"], "Expected generated improvements for the synthetic demo"
        best = recommended["recommendations"][0]
        assert best["predicted"]["unretained_runoff_m3"] < prediction["variants"]["development"]["unretained_runoff_m3"]
        assert best["estimated_cost_vnd"] <= improvement_constraints(prediction["site_area_m2"])["budget_vnd"]
        report["api"]["building_prediction_and_recommendation"] = {
            "prediction_id":prediction["id"],"recommendation_id":recommended["id"],
            "verdict":prediction["impact_assessment"]["verdict"],"status":recommended["recommendation_status"],
            "generated_suggestions":len(recommended["recommendations"]),"estimated_cost_vnd":best["estimated_cost_vnd"],
            "remaining_failures":best["remaining_failures"],
            "predicted":{key:best["predicted"][key] for key in
                         ("unretained_runoff_m3","peak_vehicle_trips_per_hour","water_demand_m3_per_day","wastewater_m3_per_day","peak_power_kw")}}
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    finally:
        report_name = 'khoi-api-smoke-report.json' if args.api_only else 'khoi-local-report.json'
        (output/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
