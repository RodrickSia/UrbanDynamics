"""WorldPop source URLs and local extraction settings."""

from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


WORLDPOP_YEARS = tuple(range(2015, 2031))
WORLDPOP_URL_TEMPLATE = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
    "{year}/VNM/v1/100m/constrained/vnm_pop_{year}_CN_100m_R2025A_v1.tif"
)
OVERTURE_RELEASE = "2026-09-23.1"
OVERTURE_RELEASE_PATH = (
    f"s3://overturemaps-us-west-2/release/{OVERTURE_RELEASE}"
)


def _worldpop_population_paths() -> dict[int, HttpUrl]:
    return {
        year: HttpUrl(WORLDPOP_URL_TEMPLATE.format(year=year))
        for year in WORLDPOP_YEARS
    }


class WorldPop(BaseModel):
    """Vietnam constrained 100 m population rasters, indexed by year."""

    population_paths: dict[int, HttpUrl] = Field(
        default_factory=_worldpop_population_paths
    )


class Overture(BaseModel):
    """Overture GeoParquet paths for HCMC buildings and its boundary."""

    release: str = OVERTURE_RELEASE
    buildings_path: str = (
        f"{OVERTURE_RELEASE_PATH}/theme=buildings/type=building/*"
    )
    division_areas_path: str = (
        f"{OVERTURE_RELEASE_PATH}/theme=divisions/type=division_area/*"
    )
    city_name: str = "Thành phố Hồ Chí Minh"
    country_code: str = "VN"
    # Broad prefilter for the expanded HCMC administrative area, including Con Dao.
    # The final selection is clipped by the Overture division-area geometry.
    search_bbox: tuple[float, float, float, float] = (105.5, 8.0, 109.0, 12.0)
    buildings_output_path: Path = Path(
        "data/population_hcmc/overture/buildings_2026-09-23.1.parquet"
    )


class PopulationHCMCConfig(BaseModel):
    worldpop: WorldPop = Field(default_factory=WorldPop)
    overture: Overture = Field(default_factory=Overture)
    download_dir: Path = Path("data/population_hcmc/worldpop")


config = PopulationHCMCConfig()
