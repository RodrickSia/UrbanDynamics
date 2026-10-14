"""Minimum-provision checks; kept separate from operational demand forecasts."""
import json
import math
from pathlib import Path

from ..integrated.context import digest
from ..integrated.geometry import analyze


def catalog():
    value = json.loads(Path(__file__).with_name("vietnam_catalog.json").read_text(encoding="utf-8"))
    value["sha256"] = digest(value)
    return value


def interpolate(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            fraction = (x-xs[i-1])/(xs[i]-xs[i-1])
            return ys[i-1]+fraction*(ys[i]-ys[i-1])
    raise ValueError("Invalid interpolation axis")


def apartment_density(area, height):
    if area <= 0 or height <= 0:
        raise ValueError("Positive area and height required")
    rule = catalog()["apartment_density"]
    rows = [interpolate(rule["area_m2"], row, area) for row in rule["percent"]]
    return (interpolate(rule["area_m2"], rule["above_46_percent"], area) if height > 46
            else interpolate(rule["height_m"], rows, height))


def density_check(project):
    geometry = analyze(project.site, project.development)["metrics"]
    buildings = project.development.buildings
    supported = bool(buildings) and all(b.use == "residential" for b in buildings) and len({b.height_m for b in buildings}) == 1
    if not supported:
        return {"status": "requires_separate_assessment", "reference": "QCVN 01:2021/BXD Table 2.9", "maximum_percent": None,
                "reason": "Only same-height residential apartment assumptions are covered; mixed height/use and podium/tower designs are not automatically assessed", "legal_approval_established": False}
    height = buildings[0].height_m
    maximum = apartment_density(geometry["site_area_m2"], height)
    exceeds = geometry["building_density_percent"] > maximum+1e-7
    if height > 46 and geometry["far"] > 13+1e-7:
        exceeds = True
    return {"status": "exceeds_reference_limit" if exceeds else "within_reference_limit", "reference": "QCVN 01:2021/BXD Table 2.9",
            "assumption": "Residential buildings interpreted as apartment-group development; verify project classification",
            "proposed_percent": geometry["building_density_percent"], "maximum_percent": maximum,
            "height_m": height, "area_m2": geometry["site_area_m2"], "proposed_far": geometry["far"],
            "additional_max_far": 13 if height > 46 else None, "legal_approval_established": False}


def assess(study, state):
    rules = catalog()
    known = all(p.baseline_occupancy != "unknown" for p in study.projects) and state["resolved_background"]["normalization"]["status"] != "inclusive_population_prior_unresolved"
    residents = state["metrics"].get("residents") if known else None
    levels = []
    for level, rule in rules["schools"]["levels"].items():
        places = math.ceil(residents*rule["required_places_per_1000_residents"]/1000) if residents is not None else None
        facilities = [f for f in study.school_facilities if f.education_level == level]
        capacity_known = bool(facilities) and all(f.capacity_places is not None for f in facilities)
        available = sum(f.capacity_places-f.reserved_places for f in facilities) if capacity_known else None
        levels.append({"level": level, "places_per_1000_residents": rule["required_places_per_1000_residents"],
                       "required_places": places, "minimum_land_m2": places*rule["min_land_m2_per_place"] if places is not None else None,
                       "classified_remaining_places": available, "supply_source": "Declared classified facilities only; no inference from generic OSM schools",
                       "adequacy_status": "not_assessed", "note": "Remaining places do not establish service-area accessibility or complete school inventory"})
    active = set(state["active_project_ids"])
    radius = rules["schools"]["service_radius_m"]
    access = []
    from shapely.geometry import Point, shape
    from shapely.ops import transform
    from ..integrated.context import projection
    forward, _ = projection(shape(study.study_area.model_dump()))
    for project in study.projects:
        point = transform(forward, shape(project.site.model_dump())).centroid
        for level in rules["schools"]["levels"]:
            facilities = [f for f in study.school_facilities if f.education_level == level]
            distance = min((point.distance(transform(forward, Point(f.location))) for f in facilities), default=None)
            access.append({"project_id": project.id, "level": level, "straight_line_distance_m": distance, "service_radius_m": radius,
                           "status": "unknown_school_level_or_inventory" if distance is None else "outside_reference_radius" if distance > radius else "within_reference_radius",
                           "basis": "Parcel centroid to declared school point; not verified entrances or walk route"})
    return {"catalog_id": rules["id"], "catalog_sha256": rules["sha256"], "source_url": rules["source_url"],
            "residents_basis": residents, "water_domestic_minimum_m3_day": residents*rules["water"]["domestic_min_l_person_day"]/1000 if residents is not None else None,
            "water_minimum_l_person_day": rules["water"]["domestic_min_l_person_day"], "water_scope": rules["water"]["note"],
            "school_provision": levels, "school_radius_checks": access,
            "density_checks": [{"project_id": p.id, **density_check(p)} for p in study.projects if p.id in active],
            "legal_approval_established": False,
            "limitations": ["Minimum planning provision is separate from operational demand and observed capacity; generic schools have unknown education level.",
                            "This inner-urban profile does not apply the 1000 m terrain/low-density exception automatically.",
                            "Parcel-centroid service radius is a screening proxy; walk distance and capacity allocation remain separate outputs.",
                            "No legal approval, site-specific permission or complete compliance assessment is issued."]}
