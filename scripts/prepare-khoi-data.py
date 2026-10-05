"""Download real research inputs. Prepares flood-risk inputs; there is no standalone rainfall ETL pipeline.

Run from repo root with .venv Python; set DATA_DIR=etl/data to use the Compose ETL data mount.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ETL_SOURCE = ROOT / "etl"
if not ETL_SOURCE.is_dir():
    ETL_SOURCE = ROOT
sys.path.insert(0, str(ETL_SOURCE))
from shapely.geometry import mapping
from src.pipelines.flood_history.transform import normalize
from src.shared.data_io import data_dir, download, session, write_json
from src.shared.spatial import geographic_frame


def boundary(inspect_only=False):
    response = session().get(
        "https://dataverse.ird.fr/api/datasets/:persistentId/",
        params={"persistentId": "doi:10.23708/8Y16HU"},
        timeout=(20, 90),
    )
    response.raise_for_status()
    files = response.json()["data"]["latestVersion"]["files"]
    record = next(
        f["dataFile"]
        for f in files
        if f["dataFile"]["filename"] == "HCMC_pop_density_districts.gpkg"
    )
    path = data_dir() / "raw" / "boundaries" / record["filename"]
    provenance = download(
        f"https://dataverse.ird.fr/api/access/datafile/{record['id']}", path
    )
    frame = geographic_frame(path)
    print("District columns:", list(frame.columns))
    for column in frame.columns:
        if column != frame.geometry.name and frame[column].dtype == "object":
            print(column, list(frame[column].dropna().unique())[:30])
    if inspect_only:
        return
    aliases = {
        "quan2",
        "quan9",
        "quanthuduc",
        "district2",
        "district9",
        "thuduc",
        "thuducdistrict",
        "q2",
        "q9",
    }
    if "D_Code" in frame.columns:
        # GSO district codes: 762 Thu Duc, 763 District 9, 769 District 2.
        selected = frame[frame["D_Code"].isin([762, 763, 769])]
    else:
        selected = frame[
            frame.apply(
                lambda row: any(
                    normalize(v) in aliases
                    for k, v in row.items()
                    if k != frame.geometry.name
                ),
                axis=1,
            )
        ]
    if len(selected) != 3:
        raise ValueError(
            f"Need exactly old District 2, District 9, Thu Duc district polygons; found {len(selected)}"
        )
    geometry = selected.geometry.union_all()
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "thu-duc-historical-boundary",
                "geometry": mapping(geometry),
                "properties": {
                    "name": "Thu Duc historical city scope",
                    "derived_from": "Union of publisher 2019 District 2, District 9 and Thu Duc district polygons",
                },
            }
        ],
        "metadata": {
            "provenance": provenance,
            "license": "CC BY-NC 4.0",
            "district_codes": [762, 763, 769],
            "code_reference": "https://www.gso.gov.vn/wp-content/uploads/2019/03/KQ-toan-bo.pdf",
        },
    }
    write_json(data_dir() / "inputs" / "thu_duc_boundary.geojson", document)
    print("Boundary prepared:", geometry.bounds)


def weather():
    client = session()
    issued = datetime.now(timezone.utc).isoformat()
    for kind, endpoint, parameters in (
        ("forecast", "https://api.open-meteo.com/v1/forecast", {"forecast_days": 2}),
        (
            "history",
            "https://archive-api.open-meteo.com/v1/archive",
            {"start_date": "2016-01-01", "end_date": "2025-12-31"},
        ),
    ):
        response = client.get(
            endpoint,
            params={
                "latitude": 10.82,
                "longitude": 106.76,
                "hourly": "precipitation",
                "timezone": "Asia/Ho_Chi_Minh",
                **parameters,
            },
            timeout=(20, 180),
        )
        response.raise_for_status()
        data = response.json()
        if data["hourly_units"]["precipitation"] != "mm":
            raise ValueError("Unexpected precipitation unit")
        hours = [
            {"time": t + "+07:00", "precipitation_mm": rain}
            for t, rain in zip(
                data["hourly"]["time"], data["hourly"]["precipitation"], strict=True
            )
            if rain is not None
        ]
        # This single coordinate is a live integration input, not citywide coverage.
        document = {
            "issued_at": issued,
            "source_url": response.url,
            "stations": [
                {
                    "id": "thu-duc-test-point",
                    "longitude": 106.76,
                    "latitude": 10.82,
                    "hourly": hours,
                }
            ],
            "limitations": "One weather grid point for local integration; Duy supplies production grid.",
        }
        write_json(data_dir() / "inputs" / f"rainfall_{kind}.json", document)
        print(kind, "hours:", len(hours))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target", choices=["boundary", "inspect-boundary", "weather", "all"]
    )
    args = parser.parse_args()
    if args.target in ("boundary", "inspect-boundary", "all"):
        boundary(args.target == "inspect-boundary")
    if args.target in ("weather", "all"):
        weather()
