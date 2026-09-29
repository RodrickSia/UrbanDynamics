from pydantic import BaseModel, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorldPopSourceConfig(BaseModel):
    population_url: HttpUrl
    boundaries_url: HttpUrl


class PopulationHCMCConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POPULATION_HCMC_",
        env_nested_delimiter="__",
    )

    worldpop: WorldPopSourceConfig