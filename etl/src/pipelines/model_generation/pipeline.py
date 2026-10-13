"""Full residential parcel model generation workflow."""

import logging

from src.pipelines.model_generation import extract, load, transform

logger = logging.getLogger(__name__)


def run() -> int:
    extract.run()
    transform.run()
    count = load.run()
    logger.info("Model generation finished: %s synthetic residential extrusions", count)
    return count
