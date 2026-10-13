"""Explicit replacement ledger; relocation describes people, never adds them."""
from ..integrated import demand, geometry
from ..integrated.context import digest
from .parcels import registry

LOADS = ("residents", "freshwater_m3_day", "wastewater_m3_day", "energy_kwh_day", "person_trips_day")


def validate_transfers(study):
    if not study.resident_transfers:
        return
    projects = {p.id: p for p in study.projects}
    physical_ids = registry(study)
    ids = sorted(projects)
    for transfer in study.resident_transfers:
        activated = transfer.when_active_project_ids
        if not set(activated) <= projects.keys():
            raise ValueError(f"Unknown project in resident transfer {transfer.id}")
        if len({physical_ids[p] for p in activated}) != len(activated):
            raise ValueError("Resident transfer cannot activate mutually exclusive same-parcel designs")
    # Validate overlapping conditional declarations, including future options.
    for mask in range(1 << len(ids)):
        active = {p for i, p in enumerate(ids) if mask & (1 << i)}
        if len({physical_ids[p] for p in active}) != len(active):
            continue
        outgoing, incoming = {}, {}
        for transfer in study.resident_transfers:
            if not set(transfer.when_active_project_ids) <= active:
                continue
            if transfer.from_project_id:
                origin = projects[transfer.from_project_id]
                if origin.baseline_occupancy == "unknown":
                    raise ValueError("Resident transfers require a declared baseline occupancy at their origin")
                outgoing[origin.id] = outgoing.get(origin.id, 0)+transfer.residents
            if transfer.to_project_id:
                target = transfer.to_project_id
                incoming[target] = incoming.get(target, 0)+transfer.residents
        for identifier, count in outgoing.items():
            project = projects[identifier]
            retained = _retained_residents(project)
            if count > sum(b.residents for b in project.baseline.buildings)-retained:
                raise ValueError(f"Resident transfers exceed baseline residents of project {identifier}")
        for identifier, count in incoming.items():
            project = projects[identifier]
            if count > sum(b.residents for b in project.development.buildings)-_retained_residents(project):
                raise ValueError(f"Resident transfers exceed final residents of project {identifier}")


def _building_key(block):
    from shapely.geometry import shape
    from .context import canonical_numbers
    payload = block.model_dump(mode="json", exclude={"name", "footprint"})
    payload["footprint"] = shape(block.footprint.model_dump()).normalize().wkb_hex
    return digest(canonical_numbers(payload))


def _retained_residents(project):
    final_keys = {_building_key(b) for b in project.development.buildings}
    return sum(b.residents for b in project.baseline.buildings if _building_key(b) in final_keys)


def ledger(study, context, parcel_results):
    projects = {p.id: p for p in study.projects}
    physical_ids = registry(study)
    active = {p["id"] for p in parcel_results if p["active"]}
    rows = []
    for parcel in parcel_results:
        project = projects[parcel["id"]]
        analysis = geometry.analyze(project.site, project.baseline)
        before = demand.calculate(project.baseline, analysis["floor_areas"], context["library"])
        after = parcel["demand"]
        replaced = parcel["active"]
        design = project.development if replaced else project.baseline
        old_keys = {_building_key(b): b.name for b in project.baseline.buildings}
        new_keys = {_building_key(b): b.name for b in design.buildings}
        row = {"physical_parcel_id": physical_ids[project.id], "project_id": project.id,
               "utility_zone_id": project.utility_zone_id, "active": replaced,
               "occupancy_status": project.baseline_occupancy,
               "baseline_source": project.baseline_source, "baseline_source_kind": project.baseline_kind,
               "baseline_input_sha256": digest(project.baseline.model_dump(mode="json")),
               "retained_buildings": sorted(old_keys[k] for k in old_keys.keys() & new_keys.keys()),
               "retained_residents": _retained_residents(project) if replaced else before["residents"],
               "removed_or_remodeled_buildings": sorted(old_keys[k] for k in old_keys.keys()-new_keys.keys()),
               "new_or_remodeled_buildings": sorted(new_keys[k] for k in new_keys.keys()-old_keys.keys()),
               "loads": {}, "hourly_power_kw": {},
               "limitations": ["Development is the complete final parcel state, including kept buildings; accounting removal is not a demolition estimate."]}
        for key in LOADS:
            row["loads"][key] = {"baseline": before[key], "accounting_removed": before[key] if replaced else 0,
                                  "replacement_added": after[key] if replaced else 0, "final": after[key],
                                  "delta": after[key]-before[key],
                                  "certainty": "unknown" if project.baseline_occupancy == "unknown" else "scenario_input"}
        row["hourly_power_kw"] = {"baseline": before["hourly"]["power_kw"],
                                  "accounting_removed": before["hourly"]["power_kw"] if replaced else [0]*24,
                                  "replacement_added": after["hourly"]["power_kw"] if replaced else [0]*24,
                                  "final": after["hourly"]["power_kw"]}
        rows.append(row)
    transfers = [t.model_dump(mode="json") for t in sorted(study.resident_transfers, key=lambda t: t.id)
                 if set(t.when_active_project_ids) <= active]
    resolved = context["resolved_background"]
    before_people = resolved["residents"]+sum(r["loads"]["residents"]["baseline"] for r in rows)
    final_people = resolved["residents"]+sum(r["loads"]["residents"]["final"] for r in rows)
    internal = sum(t["residents"] for t in transfers if t["from_project_id"] and t["to_project_id"])
    inflow = sum(t["residents"] for t in transfers if t["from_project_id"] is None)
    outflow = sum(t["residents"] for t in transfers if t["to_project_id"] is None)
    unresolved = []
    for row in rows:
        origin = row["project_id"]
        explained = sum(t["residents"] for t in transfers if t["from_project_id"] == origin)
        remaining = row["loads"]["residents"]["baseline"]-explained-row["retained_residents"]
        if row["active"] and remaining > 0:
            unresolved.append({"project_id": origin, "residents": remaining,
                               "status": "destination_not_declared; final counts do not establish where existing residents move"})
    unknown = any(r["occupancy_status"] == "unknown" for r in rows)
    regional_loads = {}
    background = {"freshwater_m3_day": sum(z["background_freshwater_m3_day"] for z in resolved["utility_zones"]),
                  "wastewater_m3_day": sum(z["background_wastewater_m3_day"] for z in resolved["utility_zones"]),
                  "energy_kwh_day": sum(sum(z["background_power_kw"]) for z in resolved["utility_zones"])}
    for key, value in background.items():
        regional_loads[key] = {"background": value}
        regional_loads[key].update({part: sum(row["loads"][key][part] for row in rows)
                                   for part in ("baseline", "accounting_removed", "replacement_added", "final", "delta")})
        regional_loads[key]["regional_baseline"] = value+regional_loads[key]["baseline"]
        regional_loads[key]["regional_final"] = value+regional_loads[key]["final"]
        regional_loads[key]["certainty"] = "unknown" if unknown else "scenario_input"
    return {"method": "Inclusive WorldPop population prior has an unknown parcel share; raw numeric ledger is a scenario assumption, not an established population change" if study.data_mode == "demo_system" else "Background excludes registered parcels; baseline minus selected parcel baseline plus complete selected design, each physical parcel once",
            "parcels": rows, "background_basis": "inclusive_population_prior_unresolved" if study.data_mode == "demo_system" else "excludes_registered_parcels",
            "regional_loads": regional_loads,
            "background_residents": resolved["residents"], "background_normalization": resolved["normalization"],
            "population": {"baseline": before_people, "final": final_people, "net_delta": final_people-before_people,
                           "declared_internal_relocated": internal, "declared_external_inflow": inflow,
                           "declared_external_outflow": outflow,
                           "unexplained_net_change": final_people-before_people-inflow+outflow,
                           "certainty": "unknown" if unknown else "scenario_input"},
            "active_resident_transfers": transfers, "unresolved_existing_residents": unresolved,
            "transfer_policy": "Transfers describe people already included in final building counts; no additional residents, trips or utilities are added for a transfer.",
            "limitations": ["Unexplained net change is not automatically new residents or displacement. Relocation to undeclared background locations is not inferred.",
                            "Remodeled classification does not establish demolition or retained load without a detailed plan."]}
