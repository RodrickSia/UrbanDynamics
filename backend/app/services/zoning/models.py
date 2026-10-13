from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class PlanInput(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    study_area: dict
    horizon: int | None = Field(default=None, ge=2020, le=2200)


class ZoneType(Input):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    description: str = Field(default="", max_length=1000)
    uses: str = Field(default="", max_length=1000)
    max_height: float | None = Field(default=None, ge=0, le=1000)
    max_floors: int | None = Field(default=None, ge=0, le=200)
    coverage: float | None = Field(default=None, ge=0, le=100)
    far: float | None = Field(default=None, ge=0, le=100)
    setback_front: float | None = Field(default=None, ge=0, le=1000)
    setback_side: float | None = Field(default=None, ge=0, le=1000)
    setback_rear: float | None = Field(default=None, ge=0, le=1000)
    source: str = Field(default="", max_length=2000)


class Command(Input):
    revision: int = Field(ge=1)
    action: Literal[
        "add_type", "edit_type", "duplicate_type", "delete_type", "reorder_types",
        "add_scenario", "rename_scenario", "lock_scenario", "delete_scenario", "reorder_scenarios",
        "draw", "reshape", "split", "merge", "delete_zone", "assign",
        "study_area", "rename_plan", "undo", "redo",
        "save_building", "delete_building", "demolish_parcel", "restore_parcel",
        "generate_building", "undo_development", "redo_development",
    ]
    scenario_id: str | None = Field(default=None, max_length=80)
    payload: dict = Field(default_factory=dict)


class BoundaryInput(Input):
    geometry: dict
    type_id: str = Field(max_length=80)
    policy: Literal["preserve", "replace"]
    zone_id: str | None = Field(default=None, max_length=80)


class NameInput(Input):
    name: str = Field(min_length=1, max_length=120)


class ScenarioInput(NameInput):
    description: str = Field(default="", max_length=2000)


class FloorOverride(Input):
    floor: int = Field(ge=1, le=200, strict=True)
    floor_height: float = Field(gt=0, le=20)
    space_use_id: Literal["residential", "commercial", "office", "other"]
    counts_gfa: bool = True
    counts_far: bool = True


class BuildingInput(Input):
    id: str | None = Field(default=None, max_length=80)
    origin_id: str | None = Field(default=None, max_length=80)
    parcel_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    geometry: dict
    name: str = Field(default="Proposed building", min_length=1, max_length=120)
    floors: int = Field(ge=1, le=200, strict=True)
    floor_height: float = Field(gt=0, le=20)
    space_use_id: Literal["residential", "commercial", "office", "other"]
    counts_gfa: bool = True
    counts_far: bool = True
    template_id: Literal["low-rise-v1"] | None = None
    demolish: bool = False
    floor_overrides: list[FloorOverride] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_floors(self):
        numbers = [floor.floor for floor in self.floor_overrides]
        if len(set(numbers)) != len(numbers) or any(number > self.floors for number in numbers):
            raise ValueError("Floor overrides must be unique and within the building's floor count")
        return self


class GenerationInput(Input):
    parcel_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    floors: int = Field(ge=1, le=200, strict=True)
    floor_height: float = Field(gt=0, le=20)
    coverage: float = Field(gt=0, le=100)
    setback: float = Field(ge=0, le=1000)
    space_use_id: Literal["residential", "commercial", "office", "other"] = "residential"
