"""Freeze a saved Development scenario into the shared planning simulation engine."""
from collections import defaultdict
from math import ceil
from uuid import UUID

from pydantic import Field
from shapely.geometry import mapping, shape

from .models import Input
from .development import floor_stack
from ..simulation.engine import polygon_and_area
from ..simulation.models import PolygonInput
from ..simulation.planning.models import PlanningStudy


class SimulationInput(Input):
    revision: int = Field(ge=1)
    scenario_id: UUID
    residential_m2_per_person: float = Field(default=35, ge=5, le=500)
    work_m2_per_staff: float = Field(default=20, ge=5, le=500)
    visitors_per_100m2_day: float = Field(default=10, ge=0, le=1000)
    green_open_percent: float = Field(default=30, ge=0, le=100)
    rainfall_mm: float = Field(default=60, ge=0, le=300)


def polygon(value, label):
    if value["type"] != "Polygon":
        raise ValueError(f"{label} requires one connected polygon for this simulation engine")
    return PolygonInput(**value)


def building_program(building, settings):
    footprint = polygon(building["geometry"], "Building")
    area = polygon_and_area(footprint)[1]
    uses = defaultdict(float)
    floors = floor_stack(building)
    if building["floors"] > 100 or floors[-1]["top_m"] > 400:
        raise ValueError("Simulation supports buildings up to 100 floors and 400 m")
    # GFA exclusions are accounting flags, not proof that a physical floor has no demand.
    for floor in floors:
        uses["other" if floor["space_use_id"] == "commercial" else floor["space_use_id"]] += area
    programs = []
    for use, physical_area in sorted(uses.items()):
        programs.append({"use": use, "floor_area_m2": physical_area,
                         "residents": ceil(physical_area/settings.residential_m2_per_person) if use == "residential" else 0,
                         "staff": ceil(physical_area/settings.work_m2_per_staff) if use != "residential" else 0,
                         "daily_visitors": ceil(physical_area*settings.visitors_per_100m2_day/100) if use != "residential" else 0})
    return {"name": building["name"][:80], "footprint": footprint.model_dump(), "use": programs[0]["use"],
            "floors": building["floors"], "height_m": floors[-1]["top_m"],
            "gross_floor_area_m2": area*sum(f["counts_gfa"] for f in floors), "space_uses": programs,
            "residents": sum(p["residents"] for p in programs), "staff": sum(p["staff"] for p in programs),
            "daily_visitors": sum(p["daily_visitors"] for p in programs)}


def study_from_plan(plan, settings):
    scenario = next((s for s in plan["scenarios"] if s["id"] == str(settings.scenario_id)), None)
    if scenario is None:
        raise ValueError("Scenario not found")
    if scenario["kind"] != "proposal" or not scenario.get("buildings"):
        raise ValueError("Save a proposed building before running a simulation")
    region = polygon(plan["study_area"], "Study area")
    grouped = defaultdict(list)
    for building in scenario["buildings"]:
        grouped[building["parcel_id"]].append(building)
    if len(grouped) > 6:
        raise ValueError("Simulation supports up to six developed parcels per scenario")
    projects = []
    for index, (parcel_id, buildings) in enumerate(sorted(grouped.items())):
        if len(buildings) > 20:
            raise ValueError("Simulation supports up to twenty buildings per developed parcel")
        parcel = plan.get("parcels", {}).get(parcel_id)
        if parcel is None:
            raise ValueError("Saved parcel snapshot is unavailable")
        clipped = mapping(shape(parcel["geometry"]).intersection(shape(plan["study_area"])))
        site = polygon(clipped, "Parcel inside the study area")
        site_area = polygon_and_area(site)[1]
        blocks = [building_program(b, settings) for b in buildings]
        roof = sum(polygon_and_area(PolygonInput(**b["footprint"]))[1] for b in blocks)
        open_area = max(0, site_area-roof)
        projects.append({"id": f"parcel_{index}", "title": f"Parcel {parcel_id}", "site": site.model_dump(),
                         "baseline": {"paved_m2": site_area}, "baseline_kind": "estimated",
                         "baseline_occupancy": "unknown",
                         "baseline_source": "Unknown existing buildings and surfaces; paved geometry placeholder, not surveyed vacant land",
                         "development": {"buildings": blocks,
                                         "green_m2": open_area*settings.green_open_percent/100,
                                         "paved_m2": open_area*(1-settings.green_open_percent/100)},
                         "utility_zone_id": "unknown"})
    return PlanningStudy(**{
        "title": f"{plan['name']} / {scenario['name']}"[:160], "mode": "cumulative",
        "study_area": region.model_dump(), "comparison_policy": "declared_programs",
        "source_note": f"Zoning plan {plan['id']}, revision {plan['revision']}, scenario {scenario['id']}. Saved parcel geometry and proposed buildings; assumed occupancy/surfaces, unknown baseline/capacity. Commercial uses Other coefficients. Demand includes physical floors excluded from GFA.",
        "conditions": {"rainfall_mm": settings.rainfall_mm}, "background_residents": 0,
        "background_vehicles_hour": 0, "projects": projects,
        "options": [{"id": "proposal", "title": scenario["name"], "active_project_ids": [p["id"] for p in projects]}],
        "utility_zones": [{"id": "unknown", "source_kind": "unknown",
                           "source": "No verified infrastructure capacity or background load; proposal-only calculation"}],
    })
