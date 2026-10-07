"""Actual Windows/Linux native solvers, Docker API and PostGIS; no ETL refresh needed."""
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

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux-checks", action="store_true")
    args = parser.parse_args()
    environment = dict(os.environ)
    password = environment.get("POSTGRES_PASSWORD")
    if not password:
        raise SystemExit("Set POSTGRES_PASSWORD before running; no hardcoded default")
    docker = shutil.which("docker") or r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    environment["TEST_DATABASE_URL"] = f"postgresql://urban:{quote(password, safe='')}@127.0.0.1:{environment.get('KHOI_DB_PORT', '55432')}/urban"
    environment.update(WAREHOUSE_HOST="127.0.0.1", WAREHOUSE_PORT=environment.get('KHOI_DB_PORT', '55432'),
                       WAREHOUSE_DATABASE="urban", WAREHOUSE_USER="urban", WAREHOUSE_PASSWORD=password, POSTGIS_TESTS="1")
    environment["SIMULATION_WORK_DIR"] = str(ROOT/".runtime"/"integrated-solvers")
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT/"etl"), str(ROOT/"backend")])
    output = ROOT/"test-results"
    output.mkdir(exist_ok=True)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "steps": [], "api": {}}

    def step(name, command):
        print("Running:", name, flush=True)
        start = time.perf_counter()
        with (output/f"integrated-{name}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, env=environment, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        report["steps"].append({"name": name, "exit_code": completed.returncode, "seconds": round(time.perf_counter()-start, 2)})
        if completed.returncode:
            print((output/f"integrated-{name}.log").read_text(encoding="utf-8")[-4000:])
            raise RuntimeError(f"{name} failed")

    base = f"http://127.0.0.1:{environment.get('KHOI_API_PORT', '8001')}"
    try:
        step("compose-build", [docker, "compose", "-p", "khoi-local", "-f", "compose.khoi.yaml", "up", "-d", "--build", "warehouse", "backend"])
        step("windows-tests", [sys.executable, "-m", "pytest", "-q", "--junitxml=test-results/integrated-windows.xml"])
        if args.linux_checks:
            step("linux-image", [docker, "build", "-t", "khoi-integrated-tests", "-f", "infra/testing/Dockerfile", "."])
            db_url = f"postgresql://urban:{quote(password, safe='')}@warehouse:5432/urban"
            linux_environment = {**environment, "TEST_DATABASE_URL": db_url}
            # Pass the database URL through environment, never shell text/logs.
            old = environment.get("TEST_DATABASE_URL")
            environment["TEST_DATABASE_URL"] = linux_environment["TEST_DATABASE_URL"]
            environment["WAREHOUSE_HOST"], environment["WAREHOUSE_PORT"] = "warehouse", "5432"
            step("linux-tests", [docker, "run", "--rm", "--network", "khoi-local_default", "-e", "TEST_DATABASE_URL",
                                  "-e", "WAREHOUSE_HOST", "-e", "WAREHOUSE_PORT", "-e", "WAREHOUSE_DATABASE", "-e", "WAREHOUSE_USER",
                                  "-e", "WAREHOUSE_PASSWORD", "-e", "POSTGIS_TESTS",
                                  "-v", f"{output}:/app/test-results", "khoi-integrated-tests"])
            environment["TEST_DATABASE_URL"] = old
            environment["WAREHOUSE_HOST"], environment["WAREHOUSE_PORT"] = "127.0.0.1", environment.get('KHOI_DB_PORT', '55432')
        for attempt in range(30):
            try:
                if requests.get(base+"/health", timeout=3).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        presets = requests.get(base+"/api/v1/scenarios/integrated/presets", timeout=15)
        presets.raise_for_status()
        prediction = requests.post(base+"/api/v1/scenarios/integrated/predict", json=presets.json()["default"], timeout=240)
        prediction.raise_for_status()
        source = prediction.json()
        recommendation = requests.post(base+f"/api/v1/scenarios/integrated/{source['id']}/recommendations", json={}, timeout=240)
        recommendation.raise_for_status()
        result = recommendation.json()
        restored = requests.get(base+f"/api/v1/scenarios/integrated/{result['id']}", timeout=15)
        assert restored.json() == result
        assert result["context"] == source["context"]
        assert all(r["scale_preserved"] for r in result["recommendations"])
        archive = requests.get(base+f"/api/v1/scenarios/integrated/{result['id']}/artifacts", timeout=30)
        assert archive.status_code == 200
        (output/"integrated-demo.zip").write_bytes(archive.content)
        (output/"integrated-demo.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        report["api"] = {"base_url": base, "prediction_id": source["id"], "recommendation_id": result["id"],
                         "storage_roundtrip": True, "context_frozen": True, "zip_bytes": len(archive.content),
                         "recommendation_status": result["recommendation_status"],
                         "proposal_metrics": source["variants"]["development"]["metrics"],
                         "recommendations": [{"name": r["name"], "cost_vnd": r["estimated_cost_vnd"],
                                              "metrics": r["predicted"]["metrics"]} for r in result["recommendations"]]}
        print("Docker API, immutable PostGIS roundtrip, real solver artifacts and recommendations passed", flush=True)
    finally:
        (output/"integrated-local-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
