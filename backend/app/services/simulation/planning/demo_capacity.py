"""Explicit fictional operating baseline on sourced geometry, never a field survey.

Fixed capacities/background loads do not depend on the proposed development.
Only population is inclusive; utility loads, traffic OD and school groups describe
the external background and exclude all registered parcels.
"""
from copy import deepcopy
import math

from shapely.geometry import shape

from ..integrated.context import digest
from .context import canonical_numbers
from .models import PlanningStudy

SOURCE = "SYNTHETIC capacity package v1; fictional operating baseline, not surveyed site data"


def apply_package(payload):
    study = deepcopy(payload)
    shares = []
    for project in study["projects"]:
        for building in project["baseline"]["buildings"]:
            # A fictional residential conversion; even the use is an assumption.
            area = building.get("gross_floor_area_m2")
            if area is None:
                from ..engine import polygon_and_area
                from ..models import PolygonInput
                area = polygon_and_area(PolygonInput(**building["footprint"]))[1] * building["floors"]
            building.update(use="residential", residents=math.floor(area/35),
                            units=math.ceil(math.floor(area/35)/3))
        project.update(baseline_kind="synthetic", baseline_occupancy="estimated",
                       baseline_source=SOURCE + "; OSM surfaces/footprints retained; assume residential use, 35 m2/person and 3 people/unit. No footprints means assumed zero mapped occupancy, not verified vacant land.")
    # Validate/default the designs before hashing their canonical representation.
    validated = PlanningStudy(**study)
    study = validated.model_dump(mode="json")
    for project in validated.projects:
        shares.append({"project_id": project.id,
                       "baseline_sha256": digest(canonical_numbers(project.baseline.model_dump(mode="json"))),
                       "residents": sum(b.residents for b in project.baseline.buildings), "source": SOURCE})
    study["background_residents"] = 1200 + sum(s["residents"] for s in shares)
    study["background_snapshot"] = {"id": "synthetic_capacity_v1", "source": SOURCE + "; external population 1200 plus explicit parcel contributions; replaces WorldPop demand prior only in this fictional case",
        "source_kind": "synthetic", "included_modules": ["population"],
        "coverage": study["study_area"], "parcels": shares}
    study["utility_zones"] = [{"id": z["id"], "source": SOURCE + "; external loads exclude registered parcels; fixed independently of building plan",
        "source_kind": "synthetic", "background_power_kw": [80.0]*24,
        "background_freshwater_m3_day": 140.0, "background_wastewater_m3_day": 112.0,
        "power_capacity_kw": 95.0, "water_capacity_m3_day": 160.0,
        "wastewater_capacity_m3_day": 128.0} for z in study["utility_zones"]]
    # Existing OSM school locations are retained; capacities are fictional.
    if not study["school_facilities"]:
        point = shape(study["study_area"]).representative_point()
        study["school_facilities"] = [{"id": "synthetic_school", "location": [point.x, point.y], "source": SOURCE}]
    for school in study["school_facilities"]:
        school.update(capacity_places=240, reserved_places=0, source=SOURCE + "; location is OSM when available; fallback location is study-area interior; 240 places, no outside reserved places")
    school = study["school_facilities"][0]
    study["background_school_groups"] = [{"id": "synthetic_external_students", "location": school["location"],
        "students": 216, "source": SOURCE + "; external 1200 residents x 18%, co-located with first school for demo; excludes parcel demand"}]
    study["source_note"] = SOURCE + "; geometry remains sourced; population/occupancy/utility loads/capacities/school demand fictional; counting prior transferred if installed; drainage remains synthetic. WorldPop retained only as context. No legal approval established."
    study["criteria"] = [{"metric": "school_unserved_students", "direction": "minimize"},
                         {"metric": "power_peak_kw", "direction": "minimize"},
                         {"metric": "unretained_runoff_m3", "direction": "minimize"}]
    return PlanningStudy(**study).model_dump(mode="json")


def sensitivity_settings(study, engine="screening"):
    prior = study.get("traffic_prior")
    peak = max(a+b for a,b in zip(prior["cars"], prior["motorcycles"])) if prior else study["background_vehicles_hour"]
    cases = [
        {"id": "low_demand", "source": "Demo lower demand coefficients; not a probability bound", "level": "low"},
        {"id": "high_demand", "source": "Demo higher demand coefficients; not a probability bound", "level": "high"},
        {"id": "capacity_minus20", "source": "Declared utilities and school capacity reduced 20%; reserved places unchanged", "utility_capacity_scale": .8, "existing_school_capacity_scale": .8},
        {"id": "rain_plus20", "source": "Declared event rainfall increased 20%; not a climate forecast", "rainfall_mm": min(300, study["conditions"]["rainfall_mm"]*1.2)},
    ]
    if peak:
        cases += [{"id": "traffic_half", "source": "Transferred OD departures x0.5; preserves hourly mix", "background_vehicles_hour": round(peak*.5)},
                  {"id": "traffic_plus25", "source": "Transferred OD departures x1.25; capped at pilot 6000/h", "background_vehicles_hour": min(6000, round(peak*1.25))}]
    return {"engine": engine, "seeds": [2026, 2027, 2028], "cases": cases}
