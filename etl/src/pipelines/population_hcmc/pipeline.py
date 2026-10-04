"""Entry point for extracting the HCMC WorldPop population inputs."""

import logging

from src.pipelines.population_hcmc import extract


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    downloaded = extract.run()
    logging.getLogger(__name__).info("Downloaded %s WorldPop population rasters:", len(downloaded))
    for year, path in downloaded.items():
        logging.getLogger(__name__).info("%s: %s", year, path)
