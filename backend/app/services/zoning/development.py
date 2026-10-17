"""Scenario-owned conceptual massing. Never changes cadastral or baseline assets."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from shapely.affinity import scale
from shapely.ops import unary_union

from .geometry import EPSILON, geojson, polygonal, projected
from .models import BuildingInput, GenerationInput

SPACE_USES = [
    {"id": "residential", "name": "Residential", "color": "#D79B8C", "default_floor_height": 3.2},
    {"id": "commercial", "name": "Commercial", "color": "#C18EAD", "default_floor_height": 4.0},
    {"id": "office", "name": "Office", "color": "#86A5C5", "default_floor_height": 3.6},
    {"id": "school", "name": "School", "color": "#E1BB66", "default_floor_height": 3.6},
    {"id": "other", "name": "Other", "color": "#8CA6AD", "default_floor_height": 3.2},
]
CATALOG = {"version": 1, "space_uses": SPACE_USES, "building_types": [
    {"id": "low-rise-v1", "version": 1, "name": "Low-rise", "floors": 2,
     "floor_height": 3.2, "space_use_id": "residential", "basis": "User assumptions"}]}
ACTIONS = {"save_building", "delete_building", "demolish_parcel", "restore_parcel",
           "undo_development", "redo_development"}


def parcel_snapshot(plan, source):
    geometry = projected(source["geometry"])
    if geometry.area <= EPSILON or geometry.intersection(projected(plan["study_area"])).area <= EPSILON:
        raise ValueError("Choose a parcel inside the study area")
    return {"id": str(source["id"]), "geometry": geojson(geometry), "area_m2": geometry.area,
            "land_use": source.get("land_use"), "source": "parcels.plot", "status": "source_unverified",
            "captured_at": datetime.now(timezone.utc).isoformat()}


def zone_site(plan, scenario, site_id):
    """Resolve the current scenario's canonical zone; never trust a stale client snapshot."""
    zone = next((z for z in scenario['zones'] if f"zone:{z['id']}" == site_id), None)
    if zone is None:
        raise ValueError('The selected zoning site no longer exists in this scenario')
    geometry = projected(zone['geometry']).intersection(projected(plan['study_area']))
    if geometry.area <= EPSILON:
        raise ValueError('The zoning site is outside the study area')
    zone_type = next(t for t in plan['types'] if t['id'] == zone['type_id'])
    return {'id': site_id, 'geometry': geojson(geometry), 'area_m2': geometry.area,
            'land_use': zone_type['code'], 'source': 'scenario.zone', 'status': 'user_proposed',
            'captured_at': scenario['updated_at']}


def validate_zone_sites(plan, scenario):
    # Boundary edits cannot orphan existing buildings or leave them outside their site.
    for item in [*scenario.get('buildings', []), *scenario.get('demolition_masks', [])]:
        if not item['parcel_id'].startswith('zone:'):
            continue
        site = zone_site(plan, scenario, item['parcel_id'])
        if not projected(site['geometry']).buffer(.001).covers(projected(item['geometry'])):
            raise ValueError('Remove development from this zoning site before changing its boundary')
        plan.setdefault('parcels', {})[site['id']] = site


def rules_for(plan, scenario, parcel):
    area = projected(parcel["geometry"]).intersection(projected(plan["study_area"]))
    # A boundary cutting the parcel is not enough evidence for one controlling rule profile.
    zones = [z for z in scenario["zones"] if projected(z["geometry"]).buffer(.001).covers(area)]
    if len(zones) != 1:
        return None
    return next((t for t in plan["types"] if t["id"] == zones[0]["type_id"]), None)


def metrics(buildings, area):
    footprints = [projected(b["geometry"]) for b in buildings]
    footprint = unary_union(footprints).area if footprints else 0.0
    spaces = [(p.area, floor) for p, b in zip(footprints, buildings) for floor in floor_stack(b)]
    gfa = sum(size for size, floor in spaces if floor["counts_gfa"])
    far_area = sum(size for size, floor in spaces if floor["counts_far"])
    uses = {s["id"]: sum(size for size, floor in spaces
                         if floor["space_use_id"] == s["id"] and floor["counts_gfa"]) for s in SPACE_USES}
    return {"footprint_m2": footprint, "gfa_m2": gfa, "far": far_area / area,
            "coverage_pct": 100 * footprint / area, "space_use_m2": uses}


def floor_stack(building):
    """Resolve sparse overrides; legacy buildings retain uniform floors."""
    defaults = {key: building[key] for key in ("floor_height", "space_use_id", "counts_gfa", "counts_far")}
    overrides = {item["floor"]: item for item in building.get("floor_overrides", [])}
    colors = {use["id"]: use["color"] for use in SPACE_USES}
    result, elevation = [], 0.0
    for number in range(1, building["floors"] + 1):
        floor = {**defaults, **overrides.get(number, {}), "floor": number}
        top = elevation + floor["floor_height"]
        result.append({**floor, "base_m": elevation, "top_m": top, "color": colors[floor["space_use_id"]]})
        elevation = top
    return result


def minimum_setback(parcel, buildings):
    """Smallest footprint-to-cadastral-boundary distance, not legal frontage."""
    boundary = projected(parcel['geometry']).boundary
    return min((projected(b.get('setback_geometry', b['geometry'])).distance(boundary) for b in buildings), default=None)


def validation(plan, scenario, parcel, buildings):
    measured = metrics(buildings, parcel["area_m2"])
    rule = rules_for(plan, scenario, parcel)
    rows = []
    for key, value, unit in (("max_height", max((b["height_m"] for b in buildings), default=0), "m"),
                             ("max_floors", max((b["floors"] for b in buildings), default=0), "floors"),
                             ("far", measured["far"], "ratio"), ("coverage", measured["coverage_pct"], "%")):
        assumption = rule.get(key) if rule else None
        rows.append({"rule": key, "actual": value, "allowed": None, "status": "UNKNOWN", "unit": unit,
                     "source": "No verified location-specific rule", "assumed_limit": assumption,
                     "assumption_status": ("PASS" if value <= assumption else "FAIL") if assumption is not None else "UNKNOWN",
                     "assumption_source": rule.get("source") if rule else None,
                     "rule_version": rule.get("version") if rule else None})
    for key in ("setbacks", "allowed_uses"):
        rows.append({"rule": key, "actual": minimum_setback(parcel, buildings) if key == 'setbacks' else None,
                     "allowed": None, "status": "UNKNOWN", "unit": "m" if key == 'setbacks' else "",
                     "source": "Frontage / verified rule unavailable", "assumed_limit": None,
                     "assumption_status": "UNKNOWN", "rule_version": None})
    return {"metrics": measured, "checks": rows, "rule_status": "UNKNOWN"}


def prepare_building(plan, scenario, payload):
    data = BuildingInput.model_validate(payload).model_dump()
    parcel = plan.get("parcels", {}).get(data["parcel_id"])
    if not parcel:
        raise ValueError("Load the source parcel before building")
    geometry = projected(data["geometry"])
    if geometry.area < 1:
        raise ValueError("Building footprint must be at least 1 m²")
    if not projected(parcel["geometry"]).buffer(.001).covers(geometry):
        raise ValueError("Building footprint must stay inside the selected parcel")
    if not projected(plan["study_area"]).buffer(.001).covers(geometry):
        raise ValueError("Building footprint must stay inside the study area")
    buildings = scenario.get("buildings", [])
    previous = next((b for b in buildings if b["id"] == data["id"]), None)
    if data["id"] and previous is None:
        raise ValueError("The building no longer exists")
    if previous and previous["parcel_id"] != data["parcel_id"]:
        raise ValueError("A building cannot be moved to a different parcel")
    if any(b["id"] != data["id"] and projected(b["geometry"]).intersection(geometry).area > EPSILON
           for b in buildings):
        raise ValueError("Building footprints overlap; move the duplicate before saving")
    data.pop("demolish")
    if previous:
        data["origin_id"] = previous.get("origin_id")
    stack = floor_stack(data)
    data.update(id=data["id"] or str(uuid4()), geometry=geojson(geometry), height_m=stack[-1]["top_m"], floor_stack=stack,
                footprint_m2=geometry.area, ground_anchor={"datum": "terrain_relative", "offset_m": 0,
                "status": "elevation_unverified"}, status="user_proposed", template_version=1 if data["template_id"] else None,
                origin="generated" if data["template_id"] else "manual", space_use_version=1,
                color=next(s["color"] for s in SPACE_USES if s["id"] == data["space_use_id"]))
    same_parcel = [b for b in buildings if b["parcel_id"] == data["parcel_id"] and b["id"] != data["id"]] + [data]
    return data, validation(plan, scenario, parcel, same_parcel)


def generate(plan, scenario, payload):
    data = GenerationInput.model_validate(payload)
    parcel = plan["parcels"][data.parcel_id]
    rule = rules_for(plan, scenario, parcel) or {}
    setbacks = [data.setback] + [rule[k] for k in ("setback_front", "setback_side", "setback_rear") if rule.get(k) is not None]
    buildable = projected(parcel["geometry"]).intersection(projected(plan["study_area"])).buffer(-max(setbacks))
    if buildable.is_empty:
        raise ValueError("No buildable area remains after setbacks")
    if buildable.geom_type == "MultiPolygon":
        buildable = max(buildable.geoms, key=lambda g: g.area)
    floors = min(data.floors, rule.get("max_floors") if rule.get("max_floors") is not None else data.floors)
    if rule.get("max_height") is not None:
        floors = min(floors, int(rule["max_height"] / data.floor_height))
    if floors < 1:
        raise ValueError("The proposed height/floor limit leaves no usable floors")
    coverage = min(data.coverage, rule.get("coverage") if rule.get("coverage") is not None else 100)
    target = parcel["area_m2"] * coverage / 100
    if rule.get("far") is not None:
        target = min(target, parcel["area_m2"] * rule["far"] / floors)
    # Shrink a bounded footprint, then intersect: concave parcels remain contained.
    ratio = min(1.0, (target / buildable.area) ** .5)
    footprint = scale(buildable, ratio, ratio).intersection(buildable)
    return prepare_building(plan, scenario, {"parcel_id": data.parcel_id, "geometry": geojson(footprint),
        "name": "Low-rise proposal", "floors": floors, "floor_height": data.floor_height,
        "space_use_id": data.space_use_id, "template_id": "low-rise-v1"})


def apply(plan, scenario, action, payload):
    before = {k: deepcopy(scenario.get(k, [])) for k in ("buildings", "demolition_masks")}
    if action in ("undo_development", "redo_development"):
        source, target = ("_dev_past", "_dev_future") if action == "undo_development" else ("_dev_future", "_dev_past")
        if not scenario.get(source):
            raise ValueError("No development changes to restore")
        scenario.setdefault(target, []).append(before)
        scenario.update(scenario[source].pop())
        return
    if action == "save_building":
        building, _ = prepare_building(plan, scenario, payload)
        scenario["buildings"] = [b for b in scenario.get("buildings", []) if b["id"] != building["id"]] + [building]
        if len(scenario["buildings"]) > 500:
            raise ValueError("A scenario supports at most 500 buildings")
        if payload.get("demolish"):
            mask_parcel(plan, scenario, building["parcel_id"])
    elif action == "delete_building":
        if payload.get("confirm") is not True:
            raise ValueError("Confirm deleting the building")
        if not any(b["id"] == payload.get("id") for b in scenario.get("buildings", [])):
            raise ValueError("Building not found")
        scenario["buildings"] = [b for b in scenario["buildings"] if b["id"] != payload["id"]]
    elif action in ("demolish_parcel", "restore_parcel"):
        if payload.get("confirm") is not True:
            raise ValueError("Confirm changing baseline visibility on this parcel")
        parcel_id = str(payload.get("parcel_id"))
        if parcel_id not in plan.get("parcels", {}):
            raise ValueError("Parcel not found")
        if action == "demolish_parcel":
            mask_parcel(plan, scenario, parcel_id)
        else:
            scenario["demolition_masks"] = [m for m in scenario.get("demolition_masks", []) if m["parcel_id"] != parcel_id]
    scenario["_dev_past"] = [*scenario.get("_dev_past", []), before][-30:]
    scenario["_dev_future"] = []


def mask_parcel(plan, scenario, parcel_id):
    if not any(m["parcel_id"] == parcel_id for m in scenario.get("demolition_masks", [])):
        geometry = polygonal(projected(plan["parcels"][parcel_id]["geometry"]).intersection(projected(plan["study_area"])))
        if geometry is None:
            raise ValueError("The demolition parcel does not intersect the study area")
        scenario.setdefault("demolition_masks", []).append({"id": str(uuid4()), "parcel_id": parcel_id,
            "geometry": geojson(geometry),
            "status": "user_proposed"})


def summary(plan, scenario):
    buildings = scenario.get("buildings", [])
    result = metrics(buildings, plan["area_m2"])
    masks = [projected(m["geometry"]) for m in scenario.get("demolition_masks", [])]
    result.update(buildings=len(buildings), demolition_m2=unary_union(masks).area if masks else 0,
                  baseline_gfa_m2=None, basis="Proposed buildings only; study-area denominator",
                  rule_status="UNKNOWN", revision=scenario.get("revision", 1), baseline_version=plan["baseline"]["version"])
    return result
