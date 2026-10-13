"""Pure commands. Imported reference information never enters the edit path."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from shapely.ops import split, unary_union

from .geometry import EPSILON, geojson, polygonal, projected, study_geometry, zone_record
from .models import BoundaryInput, Command, NameInput, PlanInput, ZoneType


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid4())


def create(data: PlanInput):
    area = study_geometry(data.study_area)
    captured = now()
    return {
        "id": new_id(), "name": data.name, "description": data.description,
        "horizon": data.horizon, "study_area": geojson(area), "area_m2": area.area,
        "revision": 1, "created_at": captured, "updated_at": captured,
        "status": "draft", "jurisdiction": "HCMC pilot", "types": [],
        "baseline": {"version": new_id(), "captured_at": captured,
                     "study_area": geojson(area),
                     "status": "unverified", "source": "No authoritative zoning snapshot imported"},
        "scenarios": [
            {"id": new_id(), "name": "Existing", "kind": "reference", "locked": True, "zones": []},
            {"id": new_id(), "name": "Scenario A", "kind": "proposal", "locked": False, "zones": []},
        ],
    }


def find(items, identifier):
    for item in items:
        if item["id"] == identifier:
            return item
    raise ValueError("The selected item no longer exists")


def editable(plan, identifier):
    scenario = find(plan["scenarios"], identifier)
    if scenario["kind"] == "reference" or scenario["locked"]:
        raise ValueError("This scenario is read-only; duplicate it to edit")
    return scenario


def boundary_change(plan, scenario, payload, revision):
    data = BoundaryInput.model_validate(payload)
    find(plan["types"], data.type_id)
    candidate = projected(data.geometry)
    incoming = polygonal(candidate.intersection(projected(plan["study_area"])))
    if incoming is None:
        raise ValueError("Draw a zone inside the study area")
    if data.zone_id:
        find(scenario["zones"], data.zone_id)
    others = [z for z in scenario["zones"] if z["id"] != data.zone_id]
    occupied = unary_union([projected(z["geometry"]) for z in others])
    overlap = incoming.intersection(occupied).area
    affected = [z["id"] for z in others if incoming.intersection(projected(z["geometry"])).area > EPSILON]
    result = []
    if data.policy == "preserve":
        incoming = polygonal(incoming.difference(occupied))
        result = deepcopy(others)
    else:
        for zone in others:
            if zone["id"] not in affected:
                result.append(deepcopy(zone))
                continue
            clipped = polygonal(projected(zone["geometry"]).difference(incoming))
            if clipped is not None:
                result.append(zone_record(clipped, zone["type_id"], zone["id"], revision))
    if incoming is None:
        raise ValueError("No unassigned area remains; choose Replace to change existing zones")
    result.append(zone_record(incoming, data.type_id, data.zone_id or new_id(), revision))
    if len(result) > 500:
        raise ValueError("A scenario supports at most 500 zones")
    return result, {"overlap_m2": overlap, "affected_ids": affected,
                    "clipped_outside_m2": max(0, candidate.area - candidate.intersection(
                        projected(plan["study_area"])).area), "policy": data.policy}


def apply(original, command: Command):
    plan = deepcopy(original)
    action, data = command.action, command.payload
    revision = plan["revision"] + 1
    if action in ("add_type", "edit_type", "duplicate_type", "delete_type", "reorder_types"):
        if action == "reorder_types":
            ids = data.get("ids", [])
            if len(ids) != len(plan["types"]) or set(ids) != {t["id"] for t in plan["types"]}:
                raise ValueError("Provide each type exactly once")
            plan["types"] = [find(plan["types"], i) for i in ids]
        elif action == "delete_type":
            item = find(plan["types"], data.get("id"))
            # Undo history still references types; retaining those references is intentional.
            if any(z["type_id"] == item["id"] for s in plan["scenarios"]
                   for zones in [s["zones"], *s.get("_past", []), *s.get("_future", [])] for z in zones):
                raise ValueError("This type is in use by a scenario or its undo history")
            plan["types"].remove(item)
        else:
            previous = find(plan["types"], data.get("id")) if action != "add_type" else None
            fields = data.get("type", {})
            if action == "duplicate_type":
                fields = {k: v for k, v in previous.items() if k in ZoneType.model_fields}
                fields.update({"code": data.get("code", ""), "name": data.get("name", "")})
            value = ZoneType.model_validate(fields).model_dump()
            if any(t["code"].casefold() == value["code"].casefold()
                   and (action != "edit_type" or t["id"] != previous["id"]) for t in plan["types"]):
                raise ValueError("Type code must be unique within this plan")
            if action == "edit_type":
                used = [s for s in plan["scenarios"] if any(z["type_id"] == previous["id"] for z in s["zones"])]
                if any(s["locked"] for s in used):
                    raise ValueError("A locked scenario uses this type; duplicate the type to change it")
                if len(used) > 1 and data.get("confirm_shared") is not True:
                    raise ValueError("Confirm updating this type in multiple scenarios")
                previous.update(value, version=previous["version"] + 1)
            else:
                if len(plan["types"]) >= 100:
                    raise ValueError("A plan supports at most 100 types")
                plan["types"].append({**value, "id": new_id(), "version": 1, "status": "proposal"})
    elif action == "add_scenario":
        if len(plan["scenarios"]) >= 20:
            raise ValueError("A plan supports at most 20 scenarios")
        source = find(plan["scenarios"], command.scenario_id)
        name = NameInput.model_validate(data).name
        plan["scenarios"].append({"id": new_id(), "name": name, "kind": "proposal", "locked": False,
                                  "zones": deepcopy(source["zones"]), "copied_from": source["id"]})
    elif action in ("rename_scenario", "lock_scenario", "delete_scenario"):
        scenario = find(plan["scenarios"], command.scenario_id)
        if scenario["kind"] == "reference":
            raise ValueError("Existing is an immutable reference snapshot")
        if action == "lock_scenario":
            if not isinstance(data.get("locked"), bool):
                raise ValueError("Specify whether to lock the scenario")
            scenario["locked"] = data["locked"]
        else:
            editable(plan, scenario["id"])
            if action == "rename_scenario":
                scenario["name"] = NameInput.model_validate(data).name
            else:
                if data.get("confirm") is not True:
                    raise ValueError("Confirm deleting the scenario")
                plan["scenarios"].remove(scenario)
    elif action == "rename_plan":
        plan["name"] = NameInput.model_validate(data).name
    elif action == "study_area":
        area = study_geometry(data.get("geometry"))
        if data.get("confirm") is not True:
            raise ValueError("Confirm clipping all proposal scenarios to the new study area")
        if any(s["locked"] for s in plan["scenarios"] if s["kind"] == "proposal"):
            raise ValueError("Unlock proposal scenarios before changing the study area")
        for scenario in plan["scenarios"]:
            if scenario["kind"] == "reference":
                continue
            zones = []
            for z in scenario["zones"]:
                clipped = polygonal(projected(z["geometry"]).intersection(area))
                if clipped is not None:
                    zones.append(zone_record(clipped, z["type_id"], z["id"], revision))
            scenario.update(zones=zones, _past=[], _future=[])
        plan.update(study_area=geojson(area), area_m2=area.area)
    else:
        scenario = editable(plan, command.scenario_id)
        before = deepcopy(scenario["zones"])
        if action in ("undo", "redo"):
            source, target = ("_past", "_future") if action == "undo" else ("_future", "_past")
            if not scenario.get(source):
                raise ValueError("No geometry changes to " + action)
            scenario.setdefault(target, []).append(before)
            scenario["zones"] = scenario[source].pop()
        else:
            if action in ("draw", "reshape"):
                if action == "reshape" and not data.get("zone_id"):
                    raise ValueError("Choose a zone to reshape")
                scenario["zones"], _ = boundary_change(plan, scenario, data, revision)
            elif action == "split":
                zone = find(scenario["zones"], data.get("zone_id"))
                parts = list(split(projected(zone["geometry"]), projected(data.get("geometry"), line=True)).geoms)
                if len(parts) < 2 or any(p.area <= EPSILON for p in parts):
                    raise ValueError("Draw a cut line across the selected zone")
                scenario["zones"] = [z for z in scenario["zones"] if z["id"] != zone["id"]] + [
                    zone_record(p, zone["type_id"], new_id(), revision) for p in parts]
            elif action == "merge":
                ids = data.get("zone_ids", [])
                if len(set(ids)) < 2:
                    raise ValueError("Select at least two zones to merge")
                selected = [find(scenario["zones"], i) for i in ids]
                if len({z["type_id"] for z in selected}) != 1:
                    raise ValueError("Only zones with the same type can merge")
                union = unary_union([projected(z["geometry"]) for z in selected])
                if union.geom_type != "Polygon" or not union.is_valid:
                    raise ValueError("Select adjacent zones sharing an edge")
                scenario["zones"] = [z for z in scenario["zones"] if z["id"] not in ids] + [
                    zone_record(union, selected[0]["type_id"], new_id(), revision)]
            else:
                zone = find(scenario["zones"], data.get("zone_id"))
                if action == "delete_zone":
                    if data.get("confirm") is not True:
                        raise ValueError("Confirm deleting the zone")
                    scenario["zones"].remove(zone)
                elif action == "assign":
                    find(plan["types"], data.get("type_id"))
                    zone.update(type_id=data["type_id"], revision=revision)
            if len(scenario["zones"]) > 500:
                raise ValueError("A scenario supports at most 500 zones")
            scenario["_past"] = [*scenario.get("_past", []), before][-30:]
            scenario["_future"] = []
    plan.update(revision=revision, updated_at=now())
    return plan


def present(plan):
    result = deepcopy(plan)
    for scenario in result["scenarios"]:
        scenario["can_undo"] = bool(scenario.pop("_past", []))
        scenario["can_redo"] = bool(scenario.pop("_future", []))
    return result
