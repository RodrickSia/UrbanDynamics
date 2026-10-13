"""Pinned GlobalBuildingAtlas source and warehouse settings."""

from pathlib import Path

from pydantic import BaseModel, Field

from src.pipelines.buildings_footprint.config import BOUNDARY_SOURCE

GBA_RELEASE = "9da24b3a8dce436a7420d5c3589de718d7ba14d6"
GBA_REPOSITORY = "zhu-xlab/GBA.LoD1"
GBA_TILE = "asiawest/e105_n15_e110_n10"
GBA_TILE_URL = f"https://huggingface.co/datasets/{GBA_REPOSITORY}/resolve/{GBA_RELEASE}"
GBA_POLYGONS_URL = f"{GBA_TILE_URL}/Polygon/{GBA_TILE}.geojson"
GBA_HEIGHTS_URL = f"{GBA_TILE_URL}/LoD1/{GBA_TILE}.json"


class GBABuildingsConfig(BaseModel):
    """Settings for fetching, clipping, and loading GBA LoD1 buildings."""

    city_name: str = "Ho Chi Minh City"
    dataset_release: str = GBA_RELEASE
    tile: str = GBA_TILE
    polygon_url: str = GBA_POLYGONS_URL
    heights_url: str = GBA_HEIGHTS_URL
    boundary_source: str = BOUNDARY_SOURCE
    boundary_path: Path = Path("data/buildings_footprint/hcmc_boundary.geojson")
    polygon_path: Path = Path(
        "data/buildings_footprint_gba/raw/hcmc_lod1_polygons.geojson"
    )
    heights_path: Path = Path("data/buildings_footprint_gba/raw/hcmc_lod1_heights.json")
    normalized_path: Path = Path(
        "data/buildings_footprint_gba/normalized/hcmc_lod1.geojson"
    )
    height_index_path: Path = Path("data/buildings_footprint_gba/work/heights.sqlite3")
    batch_size: int = Field(default=5000, ge=100, le=50000)
    log_interval_bytes: int = Field(default=100 * 1024 * 1024, ge=1024 * 1024)
    timeout_connect_seconds: int = Field(default=30, ge=1)
    timeout_read_seconds: int = Field(default=180, ge=1)


config = GBABuildingsConfig()
