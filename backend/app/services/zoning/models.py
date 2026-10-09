from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    max_height: float | None = Field(default=None, gt=0, le=1000)
    max_floors: int | None = Field(default=None, ge=1, le=200)
    coverage: float | None = Field(default=None, gt=0, le=100)
    far: float | None = Field(default=None, gt=0, le=100)
    setback_front: float | None = Field(default=None, ge=0, le=1000)
    setback_side: float | None = Field(default=None, ge=0, le=1000)
    setback_rear: float | None = Field(default=None, ge=0, le=1000)
    source: str = Field(default="", max_length=2000)


class Command(Input):
    revision: int = Field(ge=1)
    action: Literal[
        "add_type", "edit_type", "duplicate_type", "delete_type", "reorder_types",
        "add_scenario", "rename_scenario", "lock_scenario", "delete_scenario",
        "draw", "reshape", "split", "merge", "delete_zone", "assign",
        "study_area", "rename_plan", "undo", "redo",
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
