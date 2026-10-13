import json

from shapely.geometry import GeometryCollection
from shapely.ops import unary_union

from .engine import find
from .geometry import EPSILON, geojson, polygonal, projected


def report(plan, scenario_id, compare_id):
    current = find(plan["scenarios"], scenario_id)
    comparison = find(plan["scenarios"], compare_id or plan["scenarios"][0]["id"])
    study = projected(plan["study_area"])
    types = {t["id"]: t for t in plan["types"]}
    representatives, aliases = {}, {}
    for identifier, kind in types.items():
        fields = {k: v for k, v in kind.items() if k not in ("id", "code", "version", "origin_id")}
        signature = (kind.get("origin_id") or identifier, json.dumps(fields, sort_keys=True))
        aliases[identifier] = representatives.setdefault(signature, identifier)

    def grouped(scenario):
        result = {}
        for zone in scenario["zones"]:
            identifier = aliases.get(zone["type_id"], zone["type_id"])
            result.setdefault(identifier, []).append(projected(zone["geometry"]))
        return {key: unary_union(value) for key, value in result.items()}

    zones, before = grouped(current), grouped(comparison)
    assigned = unary_union(list(zones.values()))
    unassigned = polygonal(study.difference(assigned))
    unchanged = sum(geom.intersection(before.get(key, GeometryCollection())).area for key, geom in zones.items())
    changed = max(0, assigned.union(unary_union(list(before.values()))).area - unchanged)
    findings = [{"id": "authority", "severity": "warning", "certainty": "unknown", "zone_id": None,
                 "message": "Insufficient authoritative data for legal compliance validation."}]
    if unassigned is not None:
        findings.append({"id": "gaps", "severity": "info", "certainty": "definitive", "zone_id": None,
                         "geometry": geojson(unassigned), "message": "Unassigned study area remains."})
    rows = []
    for identifier in dict.fromkeys([*types, *zones, *before]):
        kind = types.get(identifier)
        geom = zones.get(identifier, GeometryCollection())
        area = geom.area
        reference_area = before.get(identifier, GeometryCollection()).area
        rows.append({"type_id": identifier, "area_m2": area, "comparison_m2": reference_area,
                     "delta_m2": area - reference_area,
                     "far_bound_m2": area * kind["far"] if kind and kind["far"] is not None else None,
                     "footprint_bound_m2": area * kind["coverage"] / 100 if kind and kind["coverage"] is not None else None})
    for z in current["zones"]:
        kind = types.get(z["type_id"])
        if kind is None:
            findings.append({"id": f"type-{z['id']}", "severity": "blocker", "certainty": "definitive",
                             "zone_id": z["id"], "message": "Zone has no matching type."})
        elif not kind["source"] or any(kind[k] is None for k in ("far", "coverage", "max_height", "max_floors")):
            findings.append({"id": f"metadata-{z['id']}", "severity": "info", "certainty": "unknown",
                             "zone_id": z["id"], "message": "Some rule values or their source are not available."})
        if z["area_m2"] < 1:
            findings.append({"id": f"sliver-{z['id']}", "severity": "warning", "certainty": "provisional",
                             "zone_id": z["id"], "message": "Very small zone; review possible sliver."})
    overlap = sum(z["area_m2"] for z in current["zones"]) - assigned.area
    if overlap > EPSILON:
        findings.append({"id": "overlap", "severity": "blocker", "certainty": "definitive",
                         "zone_id": None, "message": "Base-zone overlap detected."})
    return {"scenario_id": scenario_id, "compare_id": comparison["id"], "study_m2": study.area,
            "assigned_m2": assigned.area, "unassigned_m2": unassigned.area if unassigned is not None else 0,
            "changed_m2": changed, "rows": rows, "findings": findings,
            "comparison_status": "unverified reference" if comparison["kind"] == "reference" else "scenario proposal",
            "area_basis": "Gross zone area; independent scenario bounds, not buildable floor area"}
