"""WorldPop source URLs and local extraction settings."""

from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


WORLDPOP_YEARS = tuple(range(2015, 2031))
WORLDPOP_URL_TEMPLATE = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
    "{year}/VNM/v1/100m/constrained/vnm_pop_{year}_CN_100m_R2025A_v1.tif"
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


class PopulationHCMCConfig(BaseModel):
    worldpop: WorldPop = Field(default_factory=WorldPop)
    download_dir: Path = Path("data/population_hcmc/worldpop")


config = PopulationHCMCConfig()
