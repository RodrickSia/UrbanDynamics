import argparse
import json
from collections.abc import Callable

from src.pipelines.population_hcmc.pipeline import run as run_population_hcmc
from src.pipelines.rainwater.pipeline import run as run_rainwater
from src.pipelines.flood_history.pipeline import run as run_flood_history
from src.pipelines.flood_satellite.pipeline import run as run_flood_satellite
from src.pipelines.flood_risk.pipeline import run as run_flood_risk
from src.pipelines.land_price.pipeline import run as run_land_price


PIPELINES: dict[str, Callable[[], None]] = {
    "population_hcmc": run_population_hcmc,
    "rainwater": run_rainwater,
    "flood_history": run_flood_history,
    "flood_satellite": run_flood_satellite,
    "flood_risk": run_flood_risk,
    "land_price": run_land_price,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an UrbanDynamics ETL pipeline.")
    parser.add_argument("pipeline", choices=PIPELINES, help="Pipeline to run")
    parser.add_argument("--source", help="Local GeoPackage / reviewed price JSON / PDF")
    parser.add_argument("--boundary", help="WGS84 GeoJSON polygon; required for satellite")
    parser.add_argument("--segments", help="Reviewed road segment GeoJSON for price matching")
    parser.add_argument("--weather-input", help="Rainwater forecast contract JSON")
    parser.add_argument("--history-input", help="Rainwater historical contract JSON")
    parser.add_argument("--catalog-only", action="store_true", help="Verify STAC coverage without claiming flood pixels")
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 11))
    args = parser.parse_args()
    if args.pipeline in ("rainwater", "population_hcmc"):
        PIPELINES[args.pipeline]()
    else:
        result = PIPELINES[args.pipeline](**{k: v for k, v in vars(args).items() if k != "pipeline"})
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
