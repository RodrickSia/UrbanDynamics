"""Explicit pressure per declared program, preserving absolute impact rows."""
from copy import deepcopy

UNITS = {"floor_area_m2": "declared m2 GFA", "housing_units": "declared housing unit",
         "residents": "declared resident", "school_places": "declared school place",
         "office_staff": "declared office staff member"}
USES = {"housing_units": {"residential"}, "residents": {"residential"},
        "school_places": {"school"}, "office_staff": {"office"}}
METRICS = {"power_peak_kw", "energy_kwh_day", "freshwater_m3_day", "wastewater_m3_day",
           "person_trips_day", "unretained_runoff_m3", "node_flooding_m3", "runoff_peak_m3_s",
           "school_unserved_students", "green_m2", "impervious_m2"}


def attach(study, result):
    projects = {p.id: p for p in study.projects}
    for option in result["options"]+result["phases"]:
        active = [projects[key] for key in option["state"]["active_project_ids"]]
        buildings = [b for p in active for b in p.development.buildings]
        uses = sorted({b.use for b in buildings})
        parcels = {p["id"]: p for p in option["state"]["parcels"]}
        values = {"floor_area_m2": sum(parcels[p.id]["geometry"]["floor_area_m2"] for p in active),
                  "housing_units": sum(b.units for b in buildings if b.use == "residential"),
                  "residents": sum(b.residents for b in buildings if b.use == "residential"),
                  "school_places": sum(b.service_capacity for b in buildings if b.use == "school"),
                  "office_staff": sum(b.staff for b in buildings if b.use == "office")}
        option["declared_program"] = {"active_project_ids": sorted(p.id for p in active), "uses": uses,
                                       "values": values, "denominator_policy": "Gross final active development program; excludes background and inactive projects. Not net added service."}
        rows = []
        for basis in sorted(study.normalization_bases):
            denominator = values[basis]
            compatible = basis not in USES or bool(uses) and set(uses) <= USES[basis]
            for raw in option["comparison"]+option.get("drainage_comparison", []):
                if raw["metric"] not in METRICS:
                    continue
                if not compatible:
                    status, reason = "not_comparable", "Mixed or different uses cannot share this service denominator."
                elif denominator <= 0:
                    status, reason = "insufficient_data", "No positive declared service denominator in this active program."
                elif raw["delta"] is None or raw["comparability"] not in ("comparable", "scenario_only"):
                    status, reason = "insufficient_data", "Absolute impact is missing or incomparable."
                else:
                    status, reason = raw["comparability"], None
                row = deepcopy(raw)
                row.update(normalization_basis=basis, denominator=denominator, denominator_unit=UNITS[basis],
                           numerator=raw["delta"], numerator_unit=raw["unit"], numerator_kind="regional_delta_from_common_baseline",
                           value=raw["delta"]/denominator if reason is None else None,
                           unit=f"({raw['unit']})/{UNITS[basis]}", comparability=status, unavailable_reason=reason,
                           method="Common-baseline absolute delta divided by gross declared active program; not causal attribution or a capacity approval.",
                           limitations=raw["limitations"]+["Equal physical/service denominators do not make different uses equivalent benefits; ratios are not used for automatic ranking."])
                # before/after belong to the absolute comparison, not this ratio.
                for key in ("before", "after", "delta"):
                    row.pop(key, None)
                rows.append(row)
        option["normalized_comparison"] = rows
    result["normalization_policy"] = {"bases": sorted(study.normalization_bases),
                                      "numerator": "Delta from the common baseline",
                                      "denominator": "Gross final active program, not regional population or net-added program",
                                      "ranking": "Existing criteria use absolute metrics; normalized rows are explicit additional trade-offs."}
