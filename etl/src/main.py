import argparse
from collections.abc import Callable

from src.pipelines.population_hcmc.pipeline import run as run_population_hcmc
from src.pipelines.rainwater.pipeline import run as run_rainwater


PIPELINES: dict[str, Callable[[], None]] = {
    "population_hcmc": run_population_hcmc,
    "rainwater": run_rainwater,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an UrbanDynamics ETL pipeline.")
    parser.add_argument("pipeline", choices=PIPELINES, help="Pipeline to run")
    args = parser.parse_args()
    PIPELINES[args.pipeline]()


if __name__ == "__main__":
    main()
