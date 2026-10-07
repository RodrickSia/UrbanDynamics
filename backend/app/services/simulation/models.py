from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class PolygonInput(StrictModel):
    type: Literal["Polygon"]
    coordinates: list[list[tuple[float, float]]] = Field(min_length=1, max_length=20)


class Coefficients(StrictModel):
    roof: float = Field(ge=0, le=1)
    paved: float = Field(ge=0, le=1)
    permeable: float = Field(ge=0, le=1)
    green: float = Field(ge=0, le=1)


class Variant(StrictModel):
    roof_m2: float = Field(ge=0, le=1_000_000)
    paved_m2: float = Field(ge=0, le=1_000_000)
    permeable_m2: float = Field(ge=0, le=1_000_000)
    green_m2: float = Field(ge=0, le=1_000_000)
    available_storage_m3: float = Field(default=0, ge=0, le=1_000_000)
    floors: int = Field(default=1, ge=1, le=100)
    users: int = Field(default=0, ge=0, le=100_000)
    footprint: PolygonInput | None = None


class ScenarioBase(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    building_use: Literal["school", "residential", "office", "hospital", "other"]
    site: PolygonInput
    rainfall_mm: float = Field(ge=0, le=1000)
    coefficients: Coefficients
    coefficient_basis: str = Field(min_length=5, max_length=1000)
    design_basis: str = Field(min_length=5, max_length=1000)
    baseline: Variant
    development: Variant


class BuildingScenario(ScenarioBase):
    mitigated: Variant


class EvaluationTargets(StrictModel):
    allowed_runoff_increase_pct: float = Field(ge=0, le=1000)
    minimum_green_pct: float = Field(ge=0, le=100)
    maximum_impervious_pct: float = Field(ge=0, le=100)
    basis: str = Field(min_length=5, max_length=1000)


class DemandAssumptions(StrictModel):
    peak_person_trips_per_user_hour: float = Field(ge=0, le=20)
    private_vehicle_share: float = Field(ge=0, le=1)
    average_vehicle_occupancy: float = Field(ge=1, le=100)
    water_liters_per_user_day: float = Field(ge=0, le=10000)
    wastewater_fraction: float = Field(ge=0, le=1)
    peak_kw_per_user: float = Field(ge=0, le=100)
    remaining_vehicle_trips_per_hour: float = Field(ge=0, le=1_000_000)
    remaining_water_m3_per_day: float = Field(ge=0, le=1_000_000)
    remaining_wastewater_m3_per_day: float = Field(ge=0, le=1_000_000)
    remaining_power_kw: float = Field(ge=0, le=1_000_000)
    basis: str = Field(min_length=5, max_length=1000)


class BuildingPrediction(ScenarioBase):
    evaluation: EvaluationTargets
    demand: DemandAssumptions | None = None


class ImprovementConstraints(StrictModel):
    minimum_paved_m2: float = Field(ge=0, le=1_000_000)
    maximum_green_conversion_m2: float = Field(ge=0, le=1_000_000)
    maximum_permeable_conversion_m2: float = Field(ge=0, le=1_000_000)
    maximum_additional_storage_m3: float = Field(ge=0, le=1_000_000)
    budget_vnd: float = Field(ge=0, le=1e15)
    green_cost_vnd_per_m2: float = Field(gt=0, le=1e12)
    permeable_cost_vnd_per_m2: float = Field(gt=0, le=1e12)
    storage_cost_vnd_per_m3: float = Field(gt=0, le=1e12)
    cost_basis: str = Field(min_length=5, max_length=1000)
    minimum_private_vehicle_share: float = Field(default=1, ge=0, le=1)
    transport_shift_feasible: bool = False
    maximum_water_saving_fraction: float = Field(default=0, ge=0, le=.9)
    maximum_power_saving_fraction: float = Field(default=0, ge=0, le=.9)
    transport_cost_vnd_per_share_point: float = Field(default=1, gt=0, le=1e12)
    water_cost_vnd_per_saving_point: float = Field(default=1, gt=0, le=1e12)
    power_cost_vnd_per_saving_point: float = Field(default=1, gt=0, le=1e12)
