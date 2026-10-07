"""Citywide weather ETL owned by Khoi."""
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from src.shared.data_io import data_dir

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_URL = "https://archive-api.open-meteo.com/v1/archive"
SCOPE = "HCMC expanded (Ho Chi Minh, Binh Duong, Ba Ria-Vung Tau)"

@dataclass(frozen=True)
class Settings:
    boundary: Path
    grid_m: int = 10000
    batch_size: int = 10
    history_start_year: int = 2016
    history_end_year: int = field(default_factory=lambda: datetime.now(timezone.utc).year-1)
    history_stations_per_run: int = 4
    forecast_model: str = "best_match"
    history_model: str = "era5"

    def __post_init__(self):
        if not 5000 <= self.grid_m <= 50000 or not 1 <= self.batch_size <= 20:
            raise ValueError("Grid must be 5–50 km and batch size 1–20")
        if not 1940 <= self.history_start_year <= self.history_end_year:
            raise ValueError("Invalid history years")
        if self.history_stations_per_run < 1:
            raise ValueError("History budget must be positive")

def settings(boundary=None):
    return Settings(
        Path(boundary or os.getenv("HCMC_BOUNDARY", data_dir()/"inputs/hcmc_expanded_boundary.geojson")),
        grid_m=int(os.getenv("RAIN_GRID_M", "10000")),
        batch_size=int(os.getenv("RAIN_BATCH_SIZE", "10")),
        history_start_year=int(os.getenv("RAIN_HISTORY_START_YEAR", "2016")),
        history_end_year=int(os.getenv("RAIN_HISTORY_END_YEAR") or datetime.now(timezone.utc).year-1),
        history_stations_per_run=int(os.getenv("RAIN_HISTORY_STATIONS_PER_RUN", "4")),
        forecast_model=os.getenv("RAIN_FORECAST_MODEL", "best_match"),
        history_model=os.getenv("RAIN_HISTORY_MODEL", "era5"))
