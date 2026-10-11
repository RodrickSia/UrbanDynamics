"""Pinned source, study-area boundary, and warehouse settings."""

from pathlib import Path

from pydantic import BaseModel, Field

OVERTURE_RELEASE = "2026-09-23.1"
OVERTURE_RELEASE_ROOT = f"s3://overturemaps-us-west-2/release/{OVERTURE_RELEASE}"
OVERTURE_BUILDINGS_URL = f"{OVERTURE_RELEASE_ROOT}/theme=buildings/type=building/*"
BOUNDARY_SOURCE = (
    "https://raw.githubusercontent.com/vttrungeco/"
    "map-vietnamese-provinces-database/"
    "86361845ba60ee779905ef07f04d7db33c798d04/"
    "dataset-generation-scripts/resources/gis/geojson_11Mar2026/"
    "29_ho_chi_minh/province.geojson"
)


class BuildingsFootprintConfig(BaseModel):
    """Settings for fetching, normalizing, and loading Overture footprints."""

    city_name: str = "Ho Chi Minh City"
    overture_release: str = OVERTURE_RELEASE
    overture_buildings_path: str = OVERTURE_BUILDINGS_URL
    boundary_source: str = BOUNDARY_SOURCE
    boundary_path: Path = Path("data/buildings_footprint/hcmc_boundary.geojson")
    raw_path: Path = Path(f"data/buildings_footprint/raw/buildings_{OVERTURE_RELEASE}.parquet")
    normalized_path: Path = Path(
        f"data/buildings_footprint/normalized/buildings_{OVERTURE_RELEASE}.parquet"
    )
    bbox: tuple[float, float, float, float] = (106.327727, 8.631498, 107.56973, 11.502677)
    batch_size: int = Field(default=5000, ge=100, le=50000)
    database_schema: str = "buildings"
    footprint_table: str = "footprint"
    metadata_table: str = "snapshot_metadata"


config = BuildingsFootprintConfig()
