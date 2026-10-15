from typing import Literal

from pydantic import Field, model_validator
from shapely.geometry import Point, shape

from ..models import StrictModel, PolygonInput
from ..engine import polygon_and_area
from ..integrated.models import Design
from ..integrated.geometry import analyze

Identifier = str
NormalizationBasis = Literal["floor_area_m2", "housing_units", "residents", "school_places", "office_staff"]


class ProgramTargets(StrictModel):
    housing_units: int | None = Field(default=None, ge=0, le=50000)
    residents: int | None = Field(default=None, ge=0, le=100000)
    service_capacity: int | None = Field(default=None, ge=0, le=100000)
    floor_area_m2: float | None = Field(default=None, gt=0, le=2_000_000)


class StudyConditions(StrictModel):
    level: Literal["low", "base", "high"] = "base"
    rainfall_mm: float = Field(default=60, ge=0, le=300)
    rainfall_duration_minutes: int = Field(default=60, ge=15, le=180)
    traffic_hours: list[int] = Field(default_factory=lambda: [7, 18], min_length=1, max_length=4)
    seeds: list[int] = Field(default_factory=lambda: [2026], min_length=1, max_length=5)
    solar_date: str = Field(default="2026-04-15", pattern=r"^\d{4}-\d{2}-\d{2}$")
    coefficient_profile: Literal["reviewed", "demo"] = "reviewed"

    @model_validator(mode="after")
    def bounded_suite(self):
        from datetime import date
        date.fromisoformat(self.solar_date)
        if any(not 0 <= h <= 23 for h in self.traffic_hours) or len(set(self.traffic_hours)) != len(self.traffic_hours):
            raise ValueError("Traffic hours must be unique hours from 0 to 23")
        if any(not 0 <= seed <= 2**31-1 for seed in self.seeds) or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("Seeds must be unique nonnegative 32-bit integers")
        return self


class UtilityZone(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    source: str = Field(min_length=5, max_length=1000)
    source_kind: Literal["synthetic", "estimated", "observed", "unknown"] = "synthetic"
    background_power_kw: list[float] = Field(default_factory=lambda: [0.0]*24, min_length=24, max_length=24)
    background_freshwater_m3_day: float = Field(default=0, ge=0)
    background_wastewater_m3_day: float = Field(default=0, ge=0)
    power_capacity_kw: float | None = Field(default=None, gt=0)
    water_capacity_m3_day: float | None = Field(default=None, gt=0)
    wastewater_capacity_m3_day: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_background(self):
        if min(self.background_power_kw) < 0:
            raise ValueError("Background load cannot be negative")
        return self


class Project(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    title: str = Field(min_length=1, max_length=160)
    site: PolygonInput
    baseline: Design
    baseline_source: str = Field(min_length=5, max_length=1000)
    baseline_kind: Literal["synthetic", "estimated", "observed"] = "synthetic"
    baseline_occupancy: Literal["known", "estimated", "unknown"] = "estimated"
    development: Design
    utility_zone_id: str
    catchment_id: str = Field(default="pilot", pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")

    @model_validator(mode="after")
    def valid_geometry(self):
        analyze(self.site, self.baseline)
        analyze(self.site, self.development)
        return self


class DrainageCatchment(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    source: str = Field(min_length=5, max_length=1000)
    background_area_m2: float = Field(default=20000, ge=0, le=1_000_000)
    background_impervious_percent: float = Field(default=60, ge=0, le=100)
    trunk_diameter_m: float = Field(default=.45, ge=.1, le=3)
    branch_diameter_m: float = Field(default=.3, ge=.1, le=3)


class StudyOption(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    title: str = Field(min_length=1, max_length=160)
    active_project_ids: list[str] = Field(min_length=0, max_length=6)

    @model_validator(mode="after")
    def unique_projects(self):
        if len(set(self.active_project_ids)) != len(self.active_project_ids):
            raise ValueError("Project IDs within an option must be unique")
        return self


class StudyPhase(StudyOption):
    sequence: int = Field(ge=1, le=100)


class ResidentTransfer(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    from_project_id: str | None = None
    to_project_id: str | None = None
    residents: int = Field(gt=0, le=100000)
    when_active_project_ids: list[str] = Field(min_length=1, max_length=6)
    source: str = Field(min_length=5, max_length=1000)
    source_kind: Literal["synthetic", "estimated", "observed"] = "synthetic"

    @model_validator(mode="after")
    def coherent_transfer(self):
        if self.from_project_id is None and self.to_project_id is None:
            raise ValueError("A resident transfer must have a registered origin or destination")
        if len(set(self.when_active_project_ids)) != len(self.when_active_project_ids):
            raise ValueError("Transfer activation project IDs must be unique")
        required = {p for p in (self.from_project_id, self.to_project_id) if p is not None}
        if not required <= set(self.when_active_project_ids):
            raise ValueError("Transfer activation must include its registered origin and destination")
        return self


class SchoolFacility(StrictModel):
    education_level: Literal["unknown", "kindergarten", "primary", "lower_secondary"] = "unknown"
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    location: tuple[float, float]
    capacity_places: int | None = Field(default=None, ge=0, le=100000)
    reserved_places: int = Field(default=0, ge=0, le=100000)
    source: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def reserved_within_capacity(self):
        if self.capacity_places is not None and self.reserved_places > self.capacity_places:
            raise ValueError("Reserved school places exceed capacity")
        return self


class SchoolDemandGroup(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    location: tuple[float, float]
    students: int = Field(ge=0, le=100000)
    source: str = Field(min_length=5, max_length=1000)


class Criterion(StrictModel):
    metric: Literal["housing_units", "residents", "floor_area_m2", "green_m2", "impervious_m2",
                    "freshwater_m3_day", "wastewater_m3_day", "energy_kwh_day", "power_peak_kw",
                    "person_trips_day", "unretained_runoff_m3", "school_unserved_students",
                    "school_mean_assigned_walk_m", "mean_shaded_receiver_m2", "mean_shaded_neighbour_m2",
                    "node_flooding_m3", "runoff_peak_m3_s", "background_completed_delay_seconds"]
    direction: Literal["minimize", "maximize"]
    weight: float | None = Field(default=None, gt=0, le=100)


class AssumptionCase(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
    source: str = Field(min_length=5, max_length=1000)
    level: Literal["low", "base", "high"] | None = None
    rainfall_mm: float | None = Field(default=None, ge=0, le=300)
    background_vehicles_hour: int | None = Field(default=None, ge=0, le=6000)
    school_age_fraction: float | None = Field(default=None, ge=0, le=1)
    utility_capacity_scale: float | None = Field(default=None, gt=0, le=3)
    existing_school_capacity_scale: float | None = Field(default=None, gt=0, le=3)

    @model_validator(mode="after")
    def explicit_case(self):
        if self.id == "reference":
            raise ValueError("reference is reserved for the unchanged input case")
        if not self.model_dump(exclude={"id", "source"}, exclude_none=True):
            raise ValueError("An assumption case must declare a changed parameter")
        return self


class UncertaintySettings(StrictModel):
    engine: Literal["screening", "native"] = "native"
    seeds: list[int] = Field(default_factory=lambda: [2026, 2027, 2028], min_length=3, max_length=5)
    cases: list[AssumptionCase] = Field(default_factory=lambda: [
        AssumptionCase(id="low", source="Synthetic lower trip-generation scenario; fixed design and rain", level="low"),
        AssumptionCase(id="high", source="Synthetic higher trip-generation scenario; fixed design and rain", level="high")], min_length=1, max_length=8)
    traffic_material_delta_seconds: float = Field(default=.5, ge=0, le=600)

    @model_validator(mode="after")
    def unique_suite(self):
        if len(set(self.seeds)) != len(self.seeds) or any(not 0 <= s <= 2**31-1 for s in self.seeds):
            raise ValueError("Uncertainty seeds must be unique nonnegative 32-bit integers")
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Assumption case IDs must be unique")
        return self


class SnapshotTrafficProfile(StrictModel):
    cars: list[int] = Field(min_length=24, max_length=24)
    motorcycles: list[int] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def nonnegative_counts(self):
        if min(self.cars+self.motorcycles) < 0:
            raise ValueError("Snapshot traffic counts cannot be negative")
        return self


class SnapshotUtilityLoad(StrictModel):
    power_kw: list[float] = Field(min_length=24, max_length=24)
    freshwater_m3_day: float = Field(ge=0)
    wastewater_m3_day: float = Field(ge=0)

    @model_validator(mode="after")
    def nonnegative_power(self):
        if min(self.power_kw) < 0:
            raise ValueError("Snapshot power profile cannot be negative")
        return self


class SnapshotDrainageShare(StrictModel):
    area_m2: float = Field(gt=0)
    impervious_m2: float = Field(ge=0)

    @model_validator(mode="after")
    def valid_area(self):
        if self.impervious_m2 > self.area_m2:
            raise ValueError("Snapshot impervious area exceeds total area")
        return self


class SnapshotParcelContribution(StrictModel):
    project_id: str
    baseline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: str = Field(min_length=5, max_length=1000)
    residents: int | None = Field(default=None, ge=0)
    utilities: SnapshotUtilityLoad | None = None
    traffic: SnapshotTrafficProfile | None = None
    school_group_students: dict[str, int] | None = Field(default=None, max_length=12)
    drainage: SnapshotDrainageShare | None = None


class BackgroundSnapshot(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    source: str = Field(min_length=5, max_length=1000)
    source_kind: Literal["synthetic", "estimated", "observed"] = "synthetic"
    included_modules: list[Literal["population", "utilities", "traffic", "school", "drainage"]] = Field(min_length=1, max_length=5)
    parcels: list[SnapshotParcelContribution] = Field(min_length=1, max_length=6)
    coverage: PolygonInput
    traffic_basis: Literal["planned_external_od_departures"] = "planned_external_od_departures"
    regional_traffic: SnapshotTrafficProfile | None = None

    @model_validator(mode="after")
    def unique_modules(self):
        if len(set(self.included_modules)) != len(self.included_modules):
            raise ValueError("Snapshot included modules must be unique")
        if "traffic" in self.included_modules and self.regional_traffic is None:
            raise ValueError("Inclusive traffic snapshot needs explicit regional cars/motorcycles per hour; edge counts are not OD departures")
        if "traffic" not in self.included_modules and self.regional_traffic is not None:
            raise ValueError("Regional traffic profile requires the traffic included module")
        return self


class TrafficPrior(StrictModel):
    cars: list[int] = Field(min_length=24,max_length=24)
    motorcycles: list[int] = Field(min_length=24,max_length=24)
    source: str = Field(min_length=10,max_length=1000)
    source_kind: Literal["synthetic", "estimated"] = "estimated"
    counting_reference_id: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def bounded(self):
        if min(self.cars+self.motorcycles)<0 or any(a+b>6000 for a,b in zip(self.cars,self.motorcycles)):
            raise ValueError("Traffic prior requires 0–6000 total planned OD departures per hour")
        return self


class PlanningStudy(StrictModel):
    planning_catalog: Literal["none", "qcvn_urban_2021"] = "none"
    system_parcel_groups: dict[str, list[str]] = Field(default_factory=dict, max_length=6)
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=160)
    mode: Literal["site_selection", "cumulative"]
    study_area: PolygonInput
    data_mode: Literal["synthetic", "demo_system"] = "synthetic"
    system_snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    system_parcel_bindings: dict[str, str] = Field(default_factory=dict)
    traffic_network_mode: Literal["synthetic_corridor", "osm_snapshot"] = "synthetic_corridor"
    traffic_snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    development_context: dict = Field(default_factory=dict)
    source_note: str = Field(min_length=5, max_length=1000)
    conditions: StudyConditions = Field(default_factory=StudyConditions)
    comparison_policy: Literal["equal_program", "declared_programs"] = "equal_program"
    normalization_bases: list[NormalizationBasis] = Field(default_factory=lambda: ["floor_area_m2"], min_length=1, max_length=5)
    program_targets: ProgramTargets | None = None
    projects: list[Project] = Field(min_length=1, max_length=6)
    options: list[StudyOption] = Field(min_length=1, max_length=12)
    phases: list[StudyPhase] = Field(default_factory=list, max_length=4)
    utility_zones: list[UtilityZone] = Field(min_length=1, max_length=6)
    catchments: list[DrainageCatchment] = Field(default_factory=lambda: [DrainageCatchment(id="pilot", source="Synthetic shared catchment and pipe graph; not a mapped sewer")], min_length=1, max_length=6)
    background_vehicles_hour: int = Field(default=400, ge=0, le=6000)
    traffic_prior: TrafficPrior | None = None
    background_residents: int = Field(default=1200, ge=0, le=100000)
    resident_transfers: list[ResidentTransfer] = Field(default_factory=list, max_length=24)
    background_snapshot: BackgroundSnapshot | None = None
    school_facilities: list[SchoolFacility] = Field(default_factory=list, max_length=12)
    background_school_groups: list[SchoolDemandGroup] = Field(default_factory=list, max_length=12)
    school_age_fraction: float = Field(default=.18, ge=0, le=1)
    school_max_walk_m: float = Field(default=1200, gt=0, le=10000)
    school_walk_speed_m_s: float = Field(default=1.2, gt=0, le=3)
    criteria: list[Criterion] = Field(default_factory=list, max_length=8)
    uncertainty: UncertaintySettings | None = None

    @model_validator(mode="after")
    def coherent_study(self):
        if self.data_mode == "demo_system" and not self.system_snapshot_id:
            raise ValueError("Demo system study requires an installed snapshot ID")
        if self.system_parcel_groups:
            if self.system_parcel_bindings or any(not values or len(values) != len(set(values)) for values in self.system_parcel_groups.values()):
                raise ValueError("Use either individual bindings or unique nonempty parcel groups")
            flat = [key for values in self.system_parcel_groups.values() for key in values]
            if len(flat) != len(set(flat)) or len(flat) > 6:
                raise ValueError("Grouped projects require at most six disjoint source parcels")
        if self.data_mode == "synthetic" and (self.system_snapshot_id or self.system_parcel_bindings or self.system_parcel_groups):
            raise ValueError("System snapshot references require demo_system mode")
        if self.traffic_network_mode == "osm_snapshot" and self.data_mode != "demo_system" and not self.traffic_snapshot_id:
            raise ValueError("OSM planning network requires an installed demo system snapshot")
        if self.traffic_snapshot_id and self.traffic_network_mode != "osm_snapshot":
            raise ValueError("Local traffic snapshot requires OSM network mode")
        if len(set(self.normalization_bases)) != len(self.normalization_bases):
            raise ValueError("Normalization bases must be unique")
        region, area = polygon_and_area(self.study_area, maximum_area_m2=25_000_000)
        if area > 25_000_000:
            raise ValueError("Study exceeds the 25 km2 pilot bound")
        for group in (self.projects, self.options, self.phases, self.utility_zones, self.catchments, self.school_facilities, self.background_school_groups, self.resident_transfers):
            if len({item.id for item in group}) != len(group):
                raise ValueError("IDs must be unique within each collection")
        for item in self.school_facilities+self.background_school_groups:
            if not region.covers(Point(item.location)):
                raise ValueError("School facility/demand location is outside the study area")
        if sum(g.students for g in self.background_school_groups) > self.background_residents:
            raise ValueError("Background students exceed background residents")
        if len({c.metric for c in self.criteria}) != len(self.criteria):
            raise ValueError("Comparison criteria must use unique metrics")
        if any(c.weight is not None for c in self.criteria) and any(c.weight is None for c in self.criteria):
            raise ValueError("Specify weights for all criteria or none")
        if {x.id for x in self.options} & {x.id for x in self.phases}:
            raise ValueError("Option and phase IDs must not overlap")
        project_ids, zone_ids = {x.id for x in self.projects}, {x.id for x in self.utility_zones}
        catchment_ids = {x.id for x in self.catchments}
        for project in self.projects:
            if not region.covers(shape(project.site.model_dump())):
                raise ValueError(f"Project {project.id} is outside the study area")
            if project.utility_zone_id not in zone_ids:
                raise ValueError(f"Unknown utility zone for project {project.id}")
            if project.catchment_id not in catchment_ids:
                raise ValueError(f"Unknown catchment for project {project.id}")
        for option in self.options+self.phases:
            if not set(option.active_project_ids) <= project_ids:
                raise ValueError(f"Unknown project in option {option.id}")
            if self.mode == "site_selection" and len(option.active_project_ids) != 1:
                raise ValueError("Site selection options must activate exactly one project")
        if self.mode == "site_selection" and self.phases:
            raise ValueError("Phases belong to cumulative studies")
        if len({phase.sequence for phase in self.phases}) != len(self.phases):
            raise ValueError("Phase sequences must be unique")
        previous = set()
        for phase in sorted(self.phases, key=lambda p: p.sequence):
            current = set(phase.active_project_ids)
            if not previous <= current:
                raise ValueError("Pilot development phases must retain previously activated projects")
            previous = current
        if self.mode == "site_selection" and self.comparison_policy == "equal_program":
            if self.program_targets is None or not self.program_targets.model_dump(exclude_none=True):
                raise ValueError("Equal-program selection requires explicit program targets")
            for option in self.options:
                project = next(p for p in self.projects if p.id == option.active_project_ids[0])
                geometry = analyze(project.site, project.development)
                totals = {"housing_units": sum(b.units for b in project.development.buildings),
                          "residents": sum(b.residents for b in project.development.buildings),
                          "service_capacity": sum(b.service_capacity for b in project.development.buildings),
                          "floor_area_m2": geometry["metrics"]["floor_area_m2"]}
                for metric, target in self.program_targets.model_dump(exclude_none=True).items():
                    if abs(totals[metric]-target) > max(.01, abs(target)*1e-6):
                        raise ValueError(f"Option {option.id} does not meet equal-program target {metric}")
        from ..integrated.context import projection
        from shapely.ops import transform
        forward, _ = projection(region)
        for i, project in enumerate(self.projects):
            polygon = transform(forward, shape(project.site.model_dump()))
            for other in self.projects[:i]:
                other_polygon = transform(forward, shape(other.site.model_dump()))
                if polygon.intersection(other_polygon).area <= .01:
                    continue
                mutually_exclusive = all(not {project.id, other.id} <= set(o.active_project_ids) for o in self.options+self.phases)
                same_baseline = (project.baseline == other.baseline and
                                 project.utility_zone_id == other.utility_zone_id and
                                 project.baseline_occupancy == other.baseline_occupancy and
                                 project.catchment_id == other.catchment_id)
                if not polygon.equals(other_polygon) or not mutually_exclusive or not same_baseline:
                    raise ValueError("Overlapping projects require the same parcel/baseline and mutually exclusive options")
                if project.development.gate_lanes != other.development.gate_lanes:
                    raise ValueError("Same-parcel alternatives must use the same gate_lanes for the common physical access; lane redesign needs a separate network scenario")
        from .baseline import validate_transfers
        validate_transfers(self)
        if self.background_snapshot:
            from .background import resolve
            resolve(self)
        return self


class RunRequest(StrictModel):
    mode: Literal["screening", "native", "uncertainty"] = "screening"
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
