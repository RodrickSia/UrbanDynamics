"""Remove explicit parcel contributions from inclusive regional snapshots."""
from copy import deepcopy

from shapely.geometry import shape

from ..integrated.context import digest
from ..integrated.geometry import analyze
from .parcels import registry


def resolve(study):
    from .context import canonical_numbers
    bikes = round(study.background_vehicles_hour*.75)
    output = {"residents": study.background_residents,
              "utility_zones": [z.model_dump(mode="json") for z in sorted(study.utility_zones, key=lambda z: z.id)],
              "traffic": {"cars": [study.background_vehicles_hour-bikes]*24, "motorcycles": [bikes]*24},
              "school_groups": [g.model_dump(mode="json") for g in sorted(study.background_school_groups, key=lambda g: g.id)],
              "catchments": [c.model_dump(mode="json") for c in sorted(study.catchments, key=lambda c: c.id)]}
    if study.traffic_prior:
        output["traffic"] = {"cars": list(study.traffic_prior.cars), "motorcycles": list(study.traffic_prior.motorcycles)}
    original = deepcopy(output)
    snapshot = study.background_snapshot
    if snapshot is None:
        output["normalization"] = {"status": "already_excludes_registered_parcels", "snapshot_id": None,
                                   "removed_contributions": [], "basis": "Caller declares all background fields exclude registered parcels"}
        if study.data_mode == "demo_system":
            output["normalization"].update(status="inclusive_population_prior_unresolved",
                snapshot_id=study.system_snapshot_id,
                basis="WorldPop bbox total includes selected parcels; unknown parcel occupancy prevents exact subtraction. Population and demand changes are not established.")
        return output
    region = shape(study.study_area.model_dump())
    coverage = shape(snapshot.coverage.model_dump())
    if not coverage.is_valid or not coverage.covers(region):
        raise ValueError("Background snapshot coverage must contain the study area")
    if "traffic" in snapshot.included_modules:
        from .network import specification
        if any(not coverage.covers(shape(f["geometry"])) for f in specification(study)["map"]["features"]):
            raise ValueError("Traffic snapshot coverage does not contain the whole simulation network")
        output["traffic"] = snapshot.regional_traffic.model_dump(mode="json")
        original["traffic"] = deepcopy(output["traffic"])
    physical_ids = registry(study)
    projects = {p.id: p for p in study.projects}
    zones = {z["id"]: z for z in output["utility_zones"]}
    groups = {g["id"]: g for g in output["school_groups"]}
    catchments = {c["id"]: c for c in output["catchments"]}
    removed, seen = [], set()
    for share in sorted(snapshot.parcels, key=lambda p: p.project_id):
        if share.project_id not in projects:
            raise ValueError("Snapshot contribution refers to an unknown project")
        project = projects[share.project_id]
        physical = physical_ids[project.id]
        if physical in seen:
            raise ValueError("Snapshot duplicates a physical parcel through alternative designs")
        seen.add(physical)
        expected = digest(canonical_numbers(project.baseline.model_dump(mode="json")))
        if share.baseline_sha256 != expected:
            raise ValueError("Snapshot contribution baseline hash is stale or mismatched")
        if project.baseline_occupancy == "unknown" and set(snapshot.included_modules) & {"population", "traffic", "school"}:
            raise ValueError("Snapshot census/trips dedup requires declared baseline occupancy")
        required = {"population": "residents", "utilities": "utilities", "traffic": "traffic", "school": "school_group_students", "drainage": "drainage"}
        for module in snapshot.included_modules:
            if getattr(share, required[module]) is None:
                raise ValueError(f"Snapshot contribution is missing {module} data; no implicit zero subtraction")
        for module, field in required.items():
            if module not in snapshot.included_modules and getattr(share, field) is not None:
                raise ValueError(f"Snapshot contribution supplies {module} outside its included modules")
        if "population" in snapshot.included_modules:
            if share.residents != sum(b.residents for b in project.baseline.buildings):
                raise ValueError("Snapshot residents do not match the declared parcel baseline")
            output["residents"] -= share.residents
        if "utilities" in snapshot.included_modules:
            zone = zones[project.utility_zone_id]
            zone["background_power_kw"] = [a-b for a,b in zip(zone["background_power_kw"], share.utilities.power_kw)]
            zone["background_freshwater_m3_day"] -= share.utilities.freshwater_m3_day
            zone["background_wastewater_m3_day"] -= share.utilities.wastewater_m3_day
        if "traffic" in snapshot.included_modules:
            for kind in ("cars", "motorcycles"):
                output["traffic"][kind] = [a-b for a,b in zip(output["traffic"][kind], getattr(share.traffic, kind))]
        if "school" in snapshot.included_modules:
            if sum(share.school_group_students.values()) > sum(b.residents for b in project.baseline.buildings):
                raise ValueError("Snapshot parcel students exceed its declared residents")
            for group_id, count in share.school_group_students.items():
                if group_id not in groups or count < 0:
                    raise ValueError("Snapshot student share has an unknown group or negative count")
                groups[group_id]["students"] -= count
        if "drainage" in snapshot.included_modules:
            area = analyze(project.site, project.baseline)["metrics"]["site_area_m2"]
            if abs(share.drainage.area_m2-area) > max(.01, area*1e-6):
                raise ValueError("Snapshot drainage contribution must cover the complete registered parcel")
            catchment = catchments[project.catchment_id]
            impervious = catchment["background_area_m2"]*catchment["background_impervious_percent"]/100-share.drainage.impervious_m2
            catchment["background_area_m2"] -= share.drainage.area_m2
            if impervious < -.00001 or impervious > catchment["background_area_m2"]+.00001:
                raise ValueError("Snapshot drainage subtraction exceeds background impervious/pervious area")
            catchment["background_impervious_percent"] = max(0, impervious)/catchment["background_area_m2"]*100 if catchment["background_area_m2"] > 0 else 0
        removed.append({"physical_parcel_id": physical, **share.model_dump(mode="json")})
    numbers = [output["residents"]]+output["traffic"]["cars"]+output["traffic"]["motorcycles"]+[g["students"] for g in groups.values()]
    for zone in zones.values():
        numbers += zone["background_power_kw"]+[zone["background_freshwater_m3_day"], zone["background_wastewater_m3_day"]]
    numbers += [c["background_area_m2"] for c in catchments.values()]
    if min(numbers) < -1e-8:
        raise ValueError("Snapshot parcel contributions exceed the regional aggregate")
    for zone in zones.values():
        zone["background_power_kw"] = [max(0, value) for value in zone["background_power_kw"]]
        for key in ("background_freshwater_m3_day", "background_wastewater_m3_day"):
            zone[key] = max(0, zone[key])
    for catchment in catchments.values():
        catchment["background_area_m2"] = max(0, catchment["background_area_m2"])
    if any(a+b > 6000 for a,b in zip(output["traffic"]["cars"], output["traffic"]["motorcycles"])):
        raise ValueError("Resolved background traffic exceeds the 6,000 vehicles/hour pilot bound")
    if sum(g["students"] for g in groups.values()) > output["residents"]:
        raise ValueError("Resolved background students exceed resolved residents")
    snapshot_payload = snapshot.model_dump(mode="json")
    snapshot_payload["included_modules"] = sorted(snapshot_payload["included_modules"])
    snapshot_payload["parcels"] = sorted(snapshot_payload["parcels"], key=lambda p: p["project_id"])
    output["normalization"] = {"status": "inclusive_snapshot_normalized", "snapshot_id": snapshot.id,
                               "snapshot_sha256": digest(canonical_numbers(snapshot_payload)),
                               "source": snapshot.source, "source_kind": snapshot.source_kind,
                               "included_modules": sorted(snapshot.included_modules),
                               "original": original, "removed_contributions": removed,
                               "basis": "Subtract explicit hashed physical-parcel contributions once before evaluating any option",
                               "limitations": ["Traffic counts must be planned external OD departures; counting the same vehicle on multiple edges is not a regional departure aggregate.",
                                               "Measured snapshot contributions and coefficient-modeled baseline loads may differ; the difference is not silently calibrated away."]}
    return canonical_numbers(output)
