"""Settings for synthetic residential building generation."""

from pathlib import Path

from pydantic import BaseModel, Field


class ModelGenerationConfig(BaseModel):
    """Bound candidate parcels and make outputs reproducible between runs."""

    data_dir: Path = Path("data/model_generation")
    residential_codes: tuple[str, ...] = ("OTC", "ODT", "ONT")
    minimum_parcel_area_m2: float = Field(default=25, gt=0)
    maximum_parcel_area_m2: float = Field(default=3000, gt=0)
    minimum_observed_height_m: float = Field(default=3, gt=0)
    maximum_observed_height_m: float = Field(default=36, gt=0)
    inset_ratio: float = Field(default=0.06, gt=0, lt=0.5)
    minimum_inset_m: float = Field(default=0.6, ge=0)
    maximum_inset_m: float = Field(default=2.5, gt=0)
    storey_height_m: float = Field(default=3.2, gt=0)
    seed: str = "urbandynamics-residential-v1"
    height_source: str = "GBA LoD1 heights on explicitly residential parcels"


config = ModelGenerationConfig()
