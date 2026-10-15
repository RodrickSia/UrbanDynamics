"""Prepare the shared SUMO traffic-prediction road network before batch runs."""

import logging

from app.services.traffic_sumo_prediction import _directories, _network_file


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    data, runtime = _directories()
    network = _network_file(data, runtime)
    if not network.is_file() or network.stat().st_size == 0:
        raise RuntimeError(f"SUMO network preparation produced no usable file: {network}")
    logging.getLogger(__name__).info(
        "Reusable HCMC SUMO network ready: %s (%.1f MiB)",
        network,
        network.stat().st_size / (1024 * 1024),
    )


if __name__ == "__main__":
    main()
