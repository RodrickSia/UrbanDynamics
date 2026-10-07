from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from ..models import StrictModel, PolygonInput

Use = Literal["residential", "school", "office", "hospital", "other"]


class Building(StrictModel):
    name: str = Field(default="Building", min_length=1, max_length=80)
    use: Use = "residential"
    footprint: PolygonInput
    floors: int = Field(default=12, ge=1, le=100)
    height_m: float = Field(default=36, gt=0, le=400)
    gross_floor_area_m2: float | None = Field(default=None, gt=0, le=2_000_000)
    units: int = Field(default=0, ge=0, le=10000)
    residents: int = Field(default=0, ge=0, le=20000)
    staff: int = Field(default=0, ge=0, le=20000)
    daily_visitors: int = Field(default=0, ge=0, le=20000)
    daily_users: int = Field(default=0, ge=0, le=20000)
    service_capacity: int = Field(default=0, ge=0, le=50000)
    # Shared hourly schedule: used by visitors/staff, trips and operational loads.
    activity_profile: list[float] | None = Field(default=None, min_length=24, max_length=24)

    @model_validator(mode="after")
    def schedule(self):
        if self.activity_profile is not None and (min(self.activity_profile) < 0 or sum(self.activity_profile) <= 0):
            raise ValueError("Activity profile must be nonnegative with positive total")
        return self


class Tree(StrictModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    canopy_radius_m: float = Field(default=3, gt=0, le=30)
    height_m: float = Field(default=6, gt=0, le=50)
    stage: Literal["planted", "mature", "existing"] = "mature"


class Design(StrictModel):
    buildings: list[Building] = Field(default_factory=list, max_length=20)
    paved_m2: float = Field(default=0, ge=0, le=1_000_000)
    permeable_m2: float = Field(default=0, ge=0, le=1_000_000)
    green_m2: float = Field(default=0, ge=0, le=1_000_000)
    trees: list[Tree] = Field(default_factory=list, max_length=300)
    storage_m3: float = Field(default=0, ge=0, le=10000)
    storage_initial_m3: float = Field(default=0, ge=0, le=10000)
    storage_outlet_diameter_m: float = Field(default=.25, ge=.05, le=1)
    gate_lanes: int = Field(default=1, ge=1, le=4)
    gate_service_seconds: float = Field(default=8, ge=1, le=120)
    parking_spaces: int = Field(default=0, ge=0, le=10000)
    stagger_hours: int = Field(default=1, ge=1, le=3)
    efficient_fixtures: bool = False
    efficient_equipment: bool = False
    reuse_m3_day: float = Field(default=0, ge=0, le=10000)
    ev_chargers: int = Field(default=0, ge=0, le=1000)
    ev_charging_hour: int = Field(default=18, ge=0, le=23)
    added_road_m: float = Field(default=0, ge=0, le=2000)
    removed_road_m: float = Field(default=0, ge=0, le=2000)

    @model_validator(mode="after")
    def storage(self):
        if self.storage_initial_m3 > self.storage_m3:
            raise ValueError("Initial storage exceeds tank capacity")
        return self


class Conditions(StrictModel):
    level: Literal["low", "base", "high"] = "base"
    seed: int = Field(default=2026, ge=0, le=2**31-1)
    solar_date: date = date(2026, 4, 15)
    rainfall_mm: float | None = Field(default=None, ge=0, le=300)


class Baseline(StrictModel):
    design: Design
    source: str = Field(min_length=5, max_length=1000)


class IntegratedRequest(StrictModel):
    title: str = Field(default="Chung cư tại Thủ Đức", min_length=1, max_length=160)
    site: PolygonInput
    development: Design
    baseline: Baseline | None = None
    conditions: Conditions = Field(default_factory=Conditions)


class RecommendationRequest(StrictModel):
    budget_vnd: float | None = Field(default=None, ge=0, le=1e13)
    allow_surface_changes: bool = True
    allow_storage: bool = True
    allow_operations: bool = True
    maximum_additional_storage_m3: float = Field(default=200, ge=0, le=1000)
    maximum_surface_conversion_m2: float = Field(default=1500, ge=0, le=10000)
    minimum_paved_m2: float = Field(default=0, ge=0, le=1_000_000)
