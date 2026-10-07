"""Entry point for extracting the HCMC WorldPop population inputs."""

import logging

from src.pipelines.population_hcmc import extract, load, transform


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raw_data = extract.run()
    normalized_data = transform.run(raw_data)
    load.run(normalized_data)
