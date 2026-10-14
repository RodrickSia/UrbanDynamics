from uuid import UUID

from pydantic import Field, model_validator

from ..zoning.models import Input


class Assumptions(Input):
    net_area_factor: float = Field(default=.8, ge=.1, le=1)
    residential_m2_per_person: float = Field(default=35, ge=5, le=500)
    residential_m2_per_home: float = Field(default=70, ge=10, le=1000)
    work_m2_per_job: float = Field(default=20, ge=5, le=500)
    labour_force_percent: float = Field(default=50, ge=0, le=100)
    residential_kwh_person_day: float = Field(default=3, ge=0, le=100)
    workplace_kwh_m2_day: float = Field(default=.14, ge=0, le=10)
    residential_l_person_day: float = Field(default=120, ge=0, le=1000)
    workplace_l_job_day: float = Field(default=45, ge=0, le=1000)
    residential_waste_kg_person_day: float = Field(default=1, ge=0, le=20)
    workplace_waste_kg_job_day: float = Field(default=.5, ge=0, le=20)
    transit_radius_m: int = Field(default=500, ge=100, le=2000)


class AreaRequest(Input):
    geometry: dict
    plan_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    scenario_id: UUID | None = None
    include_scenario: bool = False
    assumptions: Assumptions = Field(default_factory=Assumptions)

    @model_validator(mode='after')
    def binding(self):
        if self.plan_id and (self.revision is None or self.scenario_id is None):
            raise ValueError('A plan requires its revision and scenario')
        if not self.plan_id and (self.include_scenario or self.scenario_id or self.revision):
            raise ValueError('Select a plan to include a scenario')
        return self
