"""Freeze a saved Development scenario into the shared planning simulation engine."""
from collections import defaultdict
from math import ceil
from uuid import UUID
from typing import Literal

from pydantic import Field
from shapely.geometry import mapping, shape

from .models import Input
from . import baseline
from .development import floor_stack
from ..simulation.engine import polygon_and_area
from ..simulation.models import PolygonInput
from ..simulation.planning.models import PlanningStudy
from ..simulation.integrated.models import MapBuildingCollection


class SimulationInput(Input):
    revision: int = Field(ge=1)
    scenario_id: UUID
    parcel_id: str | None = Field(default=None, pattern=r'^[1-9][0-9]{0,18}$')
    residential_m2_per_person: float = Field(default=35, ge=5, le=500)
    work_m2_per_staff: float = Field(default=20, ge=5, le=500)
    visitors_per_100m2_day: float = Field(default=10, ge=0, le=1000)
    green_open_percent: float = Field(default=30, ge=0, le=100)
    rainfall_mm: float = Field(default=60, ge=0, le=300)
    map_buildings: MapBuildingCollection | None = None


class SimulationRunInput(SimulationInput):
    mode: Literal['screening', 'native'] = 'screening'
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


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
    if settings.map_buildings is not None and not settings.parcel_id:
        raise ValueError('Map building context requires a selected parcel')
    scenario = next((s for s in plan["scenarios"] if s["id"] == str(settings.scenario_id)), None)
    if scenario is None:
        raise ValueError("Scenario not found")
    if scenario["kind"] != "proposal":
        raise ValueError("Save a proposed building before running a simulation")
    region = polygon(plan["study_area"], "Study area")
    grouped = defaultdict(list)
    for building in scenario.get("buildings", []):
        if settings.parcel_id is None or settings.parcel_id == building['parcel_id']:
            grouped[building["parcel_id"]].append(building)
    if settings.parcel_id:
        grouped.setdefault(settings.parcel_id, [])
    if not grouped:
        raise ValueError('Select a parcel or save a proposed building before running simulation')
    if len(grouped) > 6:
        raise ValueError("Simulation supports up to six developed parcels per scenario")
    blocks, baseline_blocks = [], []
    for parcel_id, proposals in sorted(grouped.items()):
        parcel = plan.get("parcels", {}).get(parcel_id)
        if parcel is None:
            raise ValueError("Saved parcel snapshot is unavailable")
        existing_blocks = []
        records = baseline.buildings(parcel, plan['study_area'])
        if settings.map_buildings is not None:
            records = baseline.with_map_buildings(parcel, plan['study_area'], records, settings.map_buildings)
        for source in records or []:
            parts = source['geometry']['coordinates'] if source['geometry']['type'] == 'MultiPolygon' else [source['geometry']['coordinates']]
            for coordinates in parts:
                existing_blocks.append(building_program({**source, 'name':'Existing mapped building',
                    'geometry': {'type':'Polygon','coordinates':coordinates},
                    'floor_height':source['height_m']/source['floors'], 'counts_gfa':True, 'counts_far':True}, settings))
        baseline_blocks.extend(existing_blocks)
        demolished = any(m['parcel_id'] == parcel_id for m in scenario.get('demolition_masks', []))
        blocks.extend([building_program(b, settings) for b in proposals] if proposals else [] if demolished else existing_blocks)
    if not blocks and not baseline_blocks:
        raise ValueError('No building data for this scope. Draw and save a building first.')
    if max(len(blocks), len(baseline_blocks)) > 20:
        raise ValueError('Simulation supports twenty buildings per run. Select a smaller scope.')
    # A whole-scenario run uses one study-area site. Separate source parcels can
    # overlap slightly; summing them as independent projects double counts land.
    site = polygon(mapping(shape(plan['parcels'][settings.parcel_id]['geometry']).intersection(shape(plan['study_area']))), 'Selected parcel') if settings.parcel_id else region
    site_area = polygon_and_area(site)[1]
    def design(buildings, green_percent):
        roof = sum(polygon_and_area(PolygonInput(**b['footprint']))[1] for b in buildings)
        open_area = max(0, site_area-roof)
        return {'buildings': buildings, 'green_m2': open_area*green_percent/100,
                'paved_m2': open_area*(1-green_percent/100)}
    projects = [{'id':'parcel_0', 'title':f'Parcel {settings.parcel_id}' if settings.parcel_id else 'Whole scenario',
                 'site':site.model_dump(), 'baseline':design(baseline_blocks,0), 'baseline_kind':'estimated',
                 'baseline_occupancy':'estimated' if settings.parcel_id and baseline_blocks else 'unknown',
                 'baseline_source':'Generated buildings / supplied Goong tile context; estimated heights, floors, occupancy and surfaces; inventory may be incomplete',
                 'development':design(blocks,settings.green_open_percent), 'utility_zone_id':'unknown'}]
    return PlanningStudy(**{
        "title": f"{plan['name']} / {scenario['name']}"[:160], "mode": "cumulative", "planning_catalog":"qcvn_urban_2021",
        "study_area": region.model_dump(), "comparison_policy": "declared_programs",
        "source_note": f"Zoning plan {plan['id']}, revision {plan['revision']}, scenario {scenario['id']}. Source parcels {sorted(grouped)}. Scope {settings.parcel_id or "study area"}. Selected saved buildings or generated current buildings; proposed design replaces the site program. Assumed occupancy/surfaces; baseline inventory and capacity may be incomplete. Commercial uses Other coefficients. Demand includes physical floors excluded from GFA.",
        "conditions": {"rainfall_mm": settings.rainfall_mm}, "background_residents": 0,
        "background_vehicles_hour": 0, "projects": projects,
        "options": [{"id": "proposal", "title": scenario["name"], "active_project_ids": [p["id"] for p in projects]}],
        "utility_zones": [{"id": "unknown", "source_kind": "unknown",
                           "source": "No verified infrastructure capacity or background load; proposal-only calculation"}],
    })
