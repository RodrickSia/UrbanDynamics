from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ChatRequest(Strict):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    selected_parcel_ids: list[str] = Field(default_factory=list, max_length=6)
    allow_native: bool = False
    request_id: UUID
    workspace: dict = Field(default_factory=dict)


class Search(Strict):
    minimum_area_m2: float = Field(default=500, ge=0, le=100000)
    maximum_area_m2: float = Field(default=100000, ge=500, le=100000)
    land_use_codes: list[str] = Field(default_factory=list, max_length=12)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    limit: int = Field(default=6, ge=1, le=12)

    @model_validator(mode="after")
    def coherent(self):
        if self.minimum_area_m2 > self.maximum_area_m2:
            raise ValueError("Invalid area interval")
        if self.bbox and not (-180 <= self.bbox[0] < self.bbox[2] <= 180 and -85 <= self.bbox[1] < self.bbox[3] <= 85):
            raise ValueError("Invalid geographic bounds")
        return self


class Program(Strict):
    parcel_ids: list[str] = Field(min_length=1, max_length=6)
    grouped: bool = False
    mode: Literal["site_selection", "cumulative"] = "site_selection"
    use: Literal["residential", "office", "school", "hospital"] = "residential"
    floors: int = Field(ge=1, le=100)
    floor_area_m2: float = Field(ge=100, le=500000)
    housing_units: int | None = Field(default=None, ge=0, le=10000)
    residents: int | None = Field(default=None, ge=0, le=20000)
    staff: int | None = Field(default=None, ge=0, le=20000)
    daily_users: int | None = Field(default=None, ge=0, le=20000)
    service_capacity: int | None = Field(default=None, ge=0, le=50000)
    background_mode: Literal["sourced", "synthetic_capacity_v1"] = "sourced"


class Run(Strict):
    draft_id: UUID
    mode: Literal["screening", "native"] = "screening"


class Verify(Strict):
    draft_id: UUID
    goal: Literal["water", "power", "runoff", "traffic"]
    mode: Literal["screening", "native"] = "screening"
