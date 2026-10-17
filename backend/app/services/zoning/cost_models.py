"""User-configured contract assumptions, not regulatory construction rates."""
from typing import Literal

from pydantic import Field, model_validator

from .models import Input


class CostArea(Input):
    name: str = Field(min_length=1, max_length=120)
    area_m2: float = Field(ge=0, le=1e8)
    factor: float = Field(ge=0, le=5)
    source: str = Field(default='User contract assumption', min_length=1, max_length=1000)


class CostProfile(Input):
    package: Literal['shell', 'standard', 'mid', 'premium', 'custom'] = 'standard'
    unit_price: float | None = Field(default=5300000, ge=0, le=1e9)
    rate_source: str = Field(default='User-supplied HCMC 2026 townhouse reference', min_length=1, max_length=1000)
    location_factor: float = Field(default=1, gt=0, le=10)
    access_factor: float = Field(default=1, gt=0, le=10)
    complexity_factor: float = Field(default=1, gt=0, le=10)
    foundation_factor: float = Field(default=.5, ge=0, le=2)
    roof_factor: float = Field(default=.4, ge=0, le=2)
    area_source: str = Field(default='User reference: strip foundation 50%; concrete roof 40%', min_length=1, max_length=1000)
    floor_area_m2: float | None = Field(default=None, ge=0, le=1e8)
    additional_areas: list[CostArea] = Field(default_factory=list, max_length=40)
    additional_areas_confirmed: bool = False

    @model_validator(mode='after')
    def no_implicit_overlap(self):
        if self.additional_areas and not self.additional_areas_confirmed:
            raise ValueError('Confirm additional areas do not overlap counted floors, foundation or roof')
        return self


class ExtraCost(Input):
    amount: float = Field(default=0, ge=0, le=1e15)
    included: bool = False


class CostSettings(Input):
    version: Literal[1] = 1
    profile: CostProfile = Field(default_factory=CostProfile)
    building_overrides: dict[str, CostProfile] = Field(default_factory=dict, max_length=500)
    demolition_rate: float | None = Field(default=None, ge=0, le=1e9)
    demolition_area_m2: float | None = Field(default=None, ge=0, le=1e8)
    demolition_included: bool = False
    demolition_source: str = Field(default='User demolition quote required', min_length=1, max_length=1000)
    extras: dict[Literal['piling', 'design', 'permit', 'special'], ExtraCost] = Field(default_factory=dict)
    vat_included: bool = False
    vat_pct: float = Field(default=0, ge=0, le=100)
    reserve_pct: float = Field(default=0, ge=0, le=100)
