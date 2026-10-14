"""Demo-only bridge from immutable team API snapshots to planning studies."""
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

from ..models import StrictModel, PolygonInput
from ..engine import polygon_and_area
from ..integrated.background import osm_features, baseline_from_osm
from ..integrated.context import projection
from ..integrated.models import Design
from .models import PlanningStudy, StudyConditions


def enabled():
    return os.getenv("PLANNING_SYSTEM_DEMO_ENABLED") == "1"


def directory():
    return Path(os.getenv("PLANNING_SYSTEM_SNAPSHOT_DIR", "data/simulation_snapshots"))


def load(identifier):
    if not enabled():
        raise ValueError("System snapshot integration is enabled only in the test demo")
    if len(identifier) != 64 or any(c not in "0123456789abcdef" for c in identifier):
        raise ValueError("Invalid snapshot ID")
    path = directory()/(identifier+".json")
    if not path.is_file():
        raise ValueError("System snapshot is not installed in this demo")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != identifier:
        raise ValueError("System snapshot integrity check failed")
    doc = json.loads(raw)
    if doc.get("schema_version") != 1 or len(doc.get("bbox", [])) != 4:
        raise ValueError("Unsupported system snapshot")
    return doc


def candidates(document):
    result = []
    coverage = box(*document["bbox"])
    for feature in document.get("parcels", {}).get("features", []):
        try:
            raw_geometry = feature["geometry"]
            if raw_geometry["type"] == "MultiPolygon" and len(raw_geometry["coordinates"]) == 1:
                raw_geometry = {"type": "Polygon", "coordinates": raw_geometry["coordinates"][0]}
            site = PolygonInput(**raw_geometry)
            geometry, area = polygon_and_area(site)
            if 500 <= area <= 100000 and coverage.covers(geometry):
                result.append({**feature, "geometry": raw_geometry, "demo_area_m2": area})
        except (ValueError, TypeError, KeyError):
            continue
    return result


class BuildingProgram(StrictModel):
    housing_units: int = Field(default=20, ge=1, le=10000)
    residents: int = Field(default=60, ge=1, le=20000)
    floors: int = Field(default=8, ge=1, le=100)
    floor_area_m2: float | None = Field(default=None, ge=100, le=500000)


class Prepare(BuildingProgram):
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    parcel_ids: list[str] = Field(min_length=1, max_length=6)
    conditions: StudyConditions = Field(default_factory=StudyConditions)
    mode: Literal["site_selection", "cumulative"] = "site_selection"
    equal_program: bool = False
    programs: dict[str, BuildingProgram] = Field(default_factory=dict)
    # Each item is a group of actual parcel IDs to build together.
    scenario_parcels: list[list[str]] = Field(default_factory=list, max_length=12)
    traffic_network_mode: Literal["synthetic_corridor", "osm_snapshot"] = "synthetic_corridor"
    counting_reference_id: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    traffic_peak_vehicles_hour: int | None = Field(default=None,ge=0,le=6000)
    # The map frontend can supply its own complete building plan, by parcel ID.
    developments: dict[str, Design] = Field(default_factory=dict)
    background_mode: Literal["sourced", "synthetic_capacity_v1"] = "sourced"
    sensitivity: bool = False
    sensitivity_engine: Literal["screening", "native"] = "screening"
    planning_catalog: Literal["none", "qcvn_urban_2021"] = "none"
    parcel_groups: list[list[str]] = Field(default_factory=list, max_length=6)
    group_developments: dict[str, Design] = Field(default_factory=dict, max_length=6)


def prepare(body, *, _document=None):
    document = load(body.snapshot_id) if _document is None else _document
    if body.parcel_groups:
        from .parcel_groups import prepare_grouped
        return prepare_grouped(body, document)
    if body.group_developments:
        raise ValueError("Group developments require parcel_groups")
    available = {str(f["id"]): f for f in candidates(document)}
    if len(set(body.parcel_ids)) != len(body.parcel_ids) or not set(body.parcel_ids) <= available.keys():
        raise ValueError("Choose unique eligible parcel IDs from this snapshot")
    if not set(body.developments) <= set(body.parcel_ids):
        raise ValueError("Building plan refers to a parcel not selected")
    if not set(body.programs) <= set(body.parcel_ids):
        raise ValueError("Building program refers to a parcel not selected")
    if body.equal_program and body.mode != "site_selection":
        raise ValueError("Equal-program comparison belongs to site selection")
    if body.equal_program and body.floor_area_m2 is None:
        raise ValueError("Equal-program comparison requires explicit floor area")
    if body.mode == "site_selection" and body.scenario_parcels:
        raise ValueError("Custom groups belong to cumulative mode")
    for group in body.scenario_parcels:
        if not group or len(group) != len(set(group)) or not set(group) <= set(body.parcel_ids):
            raise ValueError("Scenario groups require unique selected parcel IDs")
    buildings, greens, services = osm_features(document.get("osm", {"elements": []}))
    projects, options, bindings = [], [], {}
    for index, parcel_id in enumerate(body.parcel_ids):
        feature = available[parcel_id]
        site, area = polygon_and_area(PolygonInput(**feature["geometry"]))
        forward, backward = projection(site)
        program = body.programs.get(parcel_id, body)
        baseline, provenance = baseline_from_osm(site, area, buildings, greens, forward, backward, document.get("landcover"))
        if parcel_id in body.developments:
            design = body.developments[parcel_id].model_dump(mode="json")
        else:
            # Initial proposed plan, not a recommendation or a surveyed building.
            metric = transform(forward, site)
            lo, hi = 0., math.sqrt(metric.area)
            for _ in range(30):
                distance = (lo+hi)/2
                inset = metric.buffer(-distance, join_style=2)
                target_roof = program.floor_area_m2/program.floors if program.floor_area_m2 else metric.area*.35
                if target_roof > metric.area*.8:
                    raise ValueError("Program footprint exceeds the demo's 80 percent site-area bound; change floor area/floors or parcel")
                if inset.area > target_roof:
                    lo = distance
                else:
                    hi = distance
            inset = metric.buffer(-lo, join_style=2)
            if inset.geom_type == "MultiPolygon":
                inset = max(inset.geoms, key=lambda p: p.area)
            footprint = mapping(transform(backward, inset))
            roof = polygon_and_area(PolygonInput(**footprint))[1]
            if program.floor_area_m2 and abs(roof*program.floors-program.floor_area_m2) > max(1, program.floor_area_m2*.01):
                raise ValueError("Continuous generated footprint cannot fit the requested floor area; supply a complete building plan")
            design = {"buildings": [{"name": "Proposed apartment building", "footprint": footprint,
                       "use": "residential", "floors": program.floors, "height_m": program.floors*3,
                       "gross_floor_area_m2": program.floor_area_m2,
                       "units": program.housing_units, "residents": program.residents}],
                      "paved_m2": (area-roof)*.25, "green_m2": (area-roof)*.75}
        identifier = "P"+str(index+1)
        bindings[identifier] = parcel_id
        projects.append({"id": identifier, "title": "System parcel "+parcel_id,
                         "site": feature["geometry"], "baseline": baseline,
                         "baseline_source": "OSM footprints and historical WorldCover surfaces where installed, clipped to system parcel; incomplete inventory and unknown occupancy. Snapshot "+body.snapshot_id,
                         "baseline_kind": "estimated", "baseline_occupancy": "unknown",
                         "development": design, "utility_zone_id": "demo", "catchment_id": "pilot"})
        options.append({"id": identifier+"_only", "title": "Build on parcel "+parcel_id, "active_project_ids": [identifier]})
    phases = []
    if body.mode == "cumulative":
        reverse = {v: k for k, v in bindings.items()}
        if body.scenario_parcels:
            options = [{"id": "S"+str(i+1), "title": "Build on "+", ".join(group),
                        "active_project_ids": [reverse[key] for key in group]} for i, group in enumerate(body.scenario_parcels)]
        else:
            options += [{"id": "together_"+str(i), "title": "Build first "+str(i)+" parcels",
                         "active_project_ids": [p["id"] for p in projects[:i]]} for i in range(2, len(projects)+1)]
        steps = sorted(set(list(range(1, min(len(projects), 3)+1))+[len(projects)]))
        phases = [{"id": "phase_"+str(i+1), "title": "Stage "+str(i+1), "sequence": i+1,
                   "active_project_ids": [p["id"] for p in projects[:n]]} for i,n in enumerate(steps)]
    study = {"title": "System parcels and background — test demo only", "mode": body.mode,
             "planning_catalog": body.planning_catalog,
             "data_mode": "demo_system", "system_snapshot_id": body.snapshot_id, "system_parcel_bindings": bindings,
             "traffic_network_mode": body.traffic_network_mode,
             "study_area": mapping(box(*document["bbox"])), "conditions": body.conditions.model_dump(mode="json"),
             "comparison_policy": "equal_program" if body.equal_program else "declared_programs",
             "program_targets": {"housing_units": body.housing_units, "residents": body.residents, "floor_area_m2": body.floor_area_m2} if body.equal_program else None,
             "source_note": "System parcel/WorldPop/OSM/WorldCover snapshot inputs; OSM walking with estimated connectors; traffic OD and drainage remain assumptions, capacity unknown. Test demo only.",
             "projects": projects, "options": options, "phases": phases,
             "utility_zones": [{"id": "demo", "source": "Capacity unavailable; no verified service network", "source_kind": "unknown"}],
             "background_residents": 0, "background_vehicles_hour": 0,
             "school_facilities": [], "background_school_groups": []}
    # Keep a measured/modelled regional total separate from unknown parcel
    # occupancy. This estimate is not subtracted as if it were a parcel census.
    population = document.get("population", {}).get("statistics", {}).get("population_sum")
    if population is not None:
        if not math.isfinite(population) or population < 0 or population > 100000:
            raise ValueError("Population estimate exceeds the pilot bound")
        study["background_residents"] = round(population)
    region = box(*document["bbox"])
    from .counting_reference import prior, default_identifier
    counting_id=body.counting_reference_id or default_identifier()
    if counting_id:
        study['traffic_prior']=prior(counting_id,body.traffic_peak_vehicles_hour).model_dump(mode='json')
    elif body.traffic_peak_vehicles_hour is not None:
        study['background_vehicles_hour']=body.traffic_peak_vehicles_hour
    for service in services:
        if service["properties"].get("amenity") not in ("school", "kindergarten"):
            continue
        point = shape(service["geometry"])
        if region.covers(point) and len(study["school_facilities"]) < 12:
            study["school_facilities"].append({"id": "OSM"+str(service["properties"]["osm_id"]),
                "location": list(point.coords[0]), "capacity_places": None,
                "education_level": "kindergarten" if service["properties"].get("amenity") == "kindergarten" else "unknown",
                "source": "OSM school location; capacity and enrollment unavailable"})
    if body.background_mode == "synthetic_capacity_v1":
        from .demo_capacity import apply_package
        study = apply_package(study)
    if body.sensitivity:
        from .demo_capacity import sensitivity_settings
        study["uncertainty"] = sensitivity_settings(study, body.sensitivity_engine)
    # Missing observations remain unknown unless an explicit synthetic package is selected.
    return PlanningStudy(**study).model_dump(mode="json")


def attach_context(study, context):
    document = load(study.system_snapshot_id)
    registered = {str(f["id"]): f for f in candidates(document)}
    from .parcel_groups import bindings, union_members
    groups = bindings(study)
    if set(groups) != {p.id for p in study.projects}:
        raise ValueError("Every demo project requires a system parcel binding")
    for project in study.projects:
        members = [registered.get(key) for key in groups[project.id]]
        if any(f is None for f in members) or not shape(project.site.model_dump()).equals(shape(union_members(members))):
            raise ValueError("Project geometry does not match the selected system parcel")
    from .planning_review import review
    context["source_kind"] = "mixed_demo"
    context["system_background"] = {"snapshot_id": study.system_snapshot_id, "captured_at": document["captured_at"],
        "bbox": document["bbox"], "sources": document.get("sources", {}), "parcel_bindings": study.system_parcel_bindings, "parcel_groups": groups,
        "population": document.get("population"), "context_layers": document.get("layers", {}),
        "osm_element_count": len(document.get("osm", {}).get("elements", [])), "failures": document.get("failures", {}),
        "limitations": ["WorldPop bbox total includes selected parcels; their occupancy is unknown. It is retained as an inclusive regional prior, not a deduplicated population census; demand/traffic changes remain unavailable.",
                        "Public road topology is imported from OSM when osm_snapshot is selected; accesses, OD/turning demand and signal timings remain estimates. Otherwise the corridor is generated; no observed sewer capacity.",
                        "Flood/land-price layers are context only, not flood calibration, parcel legal applicability or a market-price prediction."],
        "osm_context": document.get("osm", {})}
    context["system_background"]["selected_parcels"] = [registered[key] for key in sorted({key for values in groups.values() for key in values})]
    from ..integrated.context import digest
    buildings, greens, _ = osm_features(document.get("osm", {}))
    quality = {}
    for project in sorted(study.projects, key=lambda p:p.id):
        site, area = polygon_and_area(project.site)
        forward, backward = projection(site)
        reconstructed, provenance = baseline_from_osm(site, area, buildings, greens, forward, backward, document.get("landcover"))
        quality[project.id] = {"provenance": provenance,
            "matches_source_reconstruction": digest(Design(**reconstructed).model_dump(mode="json")) == digest(project.baseline.model_dump(mode="json")),
            "reconstructed_baseline_sha256": digest(Design(**reconstructed).model_dump(mode="json"))}
    context["system_background"]["baseline_reconstruction"] = quality
    context["system_background"]["landcover"] = document.get("landcover", {}).get("metadata")
    if study.background_snapshot and study.background_snapshot.id == "synthetic_capacity_v1":
        context["system_background"]["capacity_package"] = {
            "id": "synthetic_capacity_v1", "source_kind": "synthetic",
            "source": study.background_snapshot.source,
            "utility_zones": [z.model_dump(mode="json") for z in sorted(study.utility_zones, key=lambda z: z.id)],
            "school_facilities": [s.model_dump(mode="json") for s in sorted(study.school_facilities, key=lambda s: s.id)]}
        context["system_background"]["limitations"][0] = "WorldPop is retained as context only. This explicit fictional case replaces demand with 1200 external residents plus hashed parcel occupancy assumptions; no occupancy survey or verified vacant land."
    context["system_background"]["limitations"].append("School walking uses installed OSM foot paths and estimated endpoint connectors; unreachable pairs remain unavailable. Capacity and enrollment are not inferred from locations.")
    reviews = []
    for project in sorted(study.projects, key=lambda p: p.id):
        members = [{"parcel_id": key, **review(project, registered[key].get("properties", {}))} for key in sorted(groups[project.id])]
        combined = dict(members[0])
        combined["source_parcel_reviews"] = members
        combined["source_parcel_ids"] = sorted(groups[project.id])
        combined["flags"] = sorted({flag for member in members for flag in member["flags"]})
        if len(members) > 1:
            combined.update(source_land_use_code=None, source_planning_land_use=None, source_plan=None, source_decision=None,
                            status="potential_conflict" if any(m["status"] == "potential_conflict" for m in members) else "requires_verification")
        if study.planning_catalog == "qcvn_urban_2021":
            from .vietnam_rules import density_check
            combined["qcvn_density_check"] = density_check(project)
        reviews.append(combined)
    context["system_background"]["planning_review"] = reviews
    if study.traffic_prior and study.traffic_prior.counting_reference_id:
        from .counting_reference import load as load_counting
        context['system_background']['counting_reference']=load_counting(study.traffic_prior.counting_reference_id)
        context['system_background']['limitations'].append('Counting clip is a historical unmapped reference for vehicle mix only; chosen peak OD rate and hourly profile are uncalibrated demo assumptions, not current site counts.')
    context["limitations"].extend(context["system_background"]["limitations"])
    context["data_coverage"]["kind"] = "mixed_demo_system_snapshot"
    context["data_coverage"]["population_prior_includes_selected_parcels"] = True
    return context
