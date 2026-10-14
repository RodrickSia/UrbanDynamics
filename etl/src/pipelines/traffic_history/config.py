"""Settings for the historical traffic observation pipeline."""

import os
from pathlib import Path

from pydantic import BaseModel


class TrafficHistoryConfig(BaseModel):
    data_dir: Path = Path(os.getenv("DATA_DIR", "data")) / "traffic_history"
    database_schema: str = "transport"
    table: str = "traffic_observation"

    @property
    def source_file(self) -> Path:
        return self.data_dir / "traffic.csv"

    @property
    def transformed_file(self) -> Path:
        return self.data_dir / "traffic_observations.csv"


config = TrafficHistoryConfig()
