"""Entry point for the HCMC land-plot pipeline."""

import logging

from src.pipelines.parcels_hcmc import extract, load, transform


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    download_dir = extract.run()
    normalized = transform.run(download_dir)
    load.run(normalized)
