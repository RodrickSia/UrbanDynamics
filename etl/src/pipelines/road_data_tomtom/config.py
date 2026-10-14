"""Settings for the TomTom road-flow pipeline."""

import os
from pathlib import Path

from pydantic import BaseModel


class TomTomConfig(BaseModel):
    data_dir: Path = Path(os.getenv("DATA_DIR", "data")) / "road_data_tomtom"
    database_schema: str = "transport"
    table: str = "tomtom_traffic_observation"

    @property
    def source_file(self) -> Path:
        return self.data_dir / "tomtom_hcmc_traffic_sample.csv"

    @property
    def transformed_file(self) -> Path:
        return self.data_dir / "tomtom_traffic_observations.csv"


config = TomTomConfig()
