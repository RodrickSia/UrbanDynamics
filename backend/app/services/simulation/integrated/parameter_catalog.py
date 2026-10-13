"""Reviewed numeric references and explicit assumptions for the demand model.

Extracted values retain their original denominator, geography and year. A source
minimum or citywide trip rate does not become a measured building coefficient.
"""
from copy import deepcopy
from datetime import date

VERSION = "demand-coefficients-1"
CHECKED_AT = "2026-10-11"
SOURCES = {
    "qcvn01_2021": {
        "title": "QCVN 01:2021/BXD", "publisher": "Government Gazette / Ministry of Construction",
        "url": "https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/5/33751/35832-1-2021599-60001-2021-tt-bxd.pdf",
        "year": 2021, "geography": "Vietnam", "source_kind": "planning_reference",
        "locator": "Sections 2.10.2 and 2.11.1; PDF pages 39 and 41",
        "valid_until": "2026-12-31", "successor_effective_from": "2027-01-01",
        "successor_notice": "https://moc.gov.vn/en/news/95350/thong-tu-ban-hanh-quy-chuan-ky-thuat-quoc-gia-ve-quy-hoach-do-thi-va-nong-thon.aspx",
        "values": {"domestic_min_l_person_day": 80, "school_min_l_student_day": 15,
                   "kindergarten_min_l_child_day": 75, "public_service_min_l_m2_day": 2,
                   "sanitary_planning_min_fraction": .8},
        "limitations": "Planning minima; not measured typical consumption, not an automatic compliance check. Review the successor for 2027 use."},
    "pub_household_2025": {
        "title": "PUB Water Conservation Campaign 2026", "publisher": "PUB Singapore",
        "url": "https://www.pub.gov.sg/Resources/News-Room/PressReleases/2026/03/Its-Everyones-Business-to-Make-Every-Drop-Count",
        "year": 2025, "published_at": "2026-03-17", "geography": "Singapore",
        "source_kind": "aggregate_observation", "locator": "Paragraph 6",
        "values": {"household_l_person_day": 141},
        "limitations": "Foreign household average, excludes a verified local building breakdown; a comparator, not the HCMC default."},
    "office_hcmc_2015": {
        "title": "Hoang et al., A study of energy consumption for office buildings in Vietnam",
        "publisher": "Proceedings of the International Conference on Evolving Cities",
        "url": "https://publications.evolvingcities.org/proc-icec/article/view/19",
        "doi": "10.55066/proc-icec.2021.19", "year": 2015, "published_at": "2022-01-31",
        "geography": "Ho Chi Minh City", "source_kind": "historical_sample_observation",
        "locator": "Abstract; HCMC combined commercial/government office annual mean",
        "values": {"electricity_kwh_m2_year": 116.4},
        "limitations": "Historical office sample, not a measurement of the proposed building. Annual mean divided by 365 is an average calendar day; hourly shape and peak remain assumptions."},
    "jica_his": {
        "title": "JICA Southern Roads and Bridges traffic survey, Appendix 1",
        "publisher": "JICA Survey Team", "url": "https://openjicareport.jica.go.jp/pdf/12305009_02.pdf",
        "year": 2013, "geography": "HCMC metropolitan study area",
        "source_kind": "historical_household_survey", "locator": "Appendix 1-5, PDF page 7; Table 1.1.5 and explanatory paragraph",
        "values": {"gross_person_trips_day_2002": 2.5, "gross_person_trips_day_2013": 3.2},
        "limitations": "All daily person trips, including non-home-based trips and non-trip-makers. Not vehicle trips, hourly road counts or building-gate crossings; not automatically applied to a site."},
}

RATE_UNITS = {
    "water_l_person_day": ("water", "L/resident/day", "Residents; indoor domestic demand"),
    "visitor_l_day": ("water", "L/visitor/day", "Daily visitor counted once in the building plan"),
    "staff_l_day": ("water", "L/staff/day", "Staff indoor use, separate from resident use"),
    "user_l_day": ("water", "L/daily_user/day", "Students/patients/users; not a hospital bed-day"),
    "energy_kwh_m2_day": ("energy", "kWh/m2_floor/calendar_day", "Total building electricity proxy per floor area; EV/reuse loads added separately"),
    "resident_trips_day": ("traffic", "person_trips/resident/day", "Scenario trips assigned to building access; not all citywide travel"),
    "visitor_trips_day": ("traffic", "person_trips/visitor/day", "Arrivals plus departures for each visitor"),
    "user_trips_day": ("traffic", "person_trips/daily_user/day", "Access trips per daily user; not trips per bed"),
    "staff_trips_day": ("traffic", "person_trips/staff/day", "Access trips per staff member; one arrival/one departure is a scenario assumption"),
}
GLOBALS = {
    "return_fraction": ("wastewater", "fraction", "Indoor sanitary flow / indoor water before reuse; excludes irrigation", 0, 1),
    "efficient_fixture_factor": ("water", "multiplier", "Applies only when efficient fixtures are selected", 0, 1),
    "efficient_equipment_factor": ("energy", "multiplier", "Applies only when efficient equipment is selected", 0, 1),
    "irrigation_l_m2_day": ("water", "L/m2_green/day", "Irrigation added separately and excluded from sanitary demand", 0, 30),
    "ev_kw": ("energy", "kW/charger", "Concurrent charger power; not building EUI", 0, 350),
    "ev_hours": ("energy", "hours/day", "Consecutive one-hour charging bins", 0, 24),
    "reuse_treatment_kwh_m3": ("energy", "kWh/m3_reused", "Daily reuse treatment electricity; one-hour allocation is assumed", 0, 20),
    "car_person_share": ("traffic", "fraction", "Share of scenario person trips by car", 0, 1),
    "motorcycle_person_share": ("traffic", "fraction", "Share of scenario person trips by motorcycle; residual modes not simulated", 0, 1),
    "car_occupancy": ("traffic", "people/car", "Converts person trips into car trips", 1, 10),
    "motorcycle_occupancy": ("traffic", "people/motorcycle", "Converts person trips into motorcycle trips", 1, 3),
    "background_vehicles_hour": ("traffic_background", "vehicles/hour", "Frozen background estimate for the selected SUMO comparison hour", 0, 10000),
}


def value_at(library, path):
    value = library
    for part in path.split("."):
        value = value[part]
    return value


def set_value(library, path, value):
    parts = path.split(".")
    target = library
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def reviewed_sources():
    result = deepcopy(SOURCES)
    for source in result.values():
        source["checked_at"] = CHECKED_AT
        source["numeric_extract_checked"] = True
    return result


def entries(library):
    """Return metadata for exactly the values in this library, including legacy runs."""
    result = {}
    existing = library.get("parameter_provenance", {})
    for use, rates in library["uses"].items():
        for rate, (group, unit, denominator) in RATE_UNITS.items():
            if rate not in rates:
                continue
            path = f"uses.{use}.{rate}"
            maximum = 5 if group == "energy" else 20 if group == "traffic" else 1000
            record = {**deepcopy(existing.get(path, {})), "parameter_id": path, "value": rates[rate],
                      "group": group, "unit": unit, "use": use, "denominator": denominator,
                      "geography": "Uncalibrated pilot assumption", "data_year": None,
                      "checked_at": CHECKED_AT, "numeric_source": None,
                      "kind": "synthetic", "value_status": "reviewed_but_unsourced_default",
                      "needs_local_calibration": True, "hard_bounds": [0, maximum],
                      "reference_anchors": [], "default_reason": "No directly applicable numeric source verified for this coefficient; explicit scenario assumption."}
            if rate == "water_l_person_day":
                record["reference_anchors"] = [{"source_id": "qcvn01_2021", "field": "domestic_min_l_person_day", "role": "planning_minimum_not_typical_demand"}]
                if use == "residential":
                    record["reference_anchors"].append({"source_id": "pub_household_2025", "field": "household_l_person_day", "role": "foreign_comparator_not_default"})
            elif rate == "user_l_day" and use == "school":
                record["reference_anchors"] = [{"source_id": "qcvn01_2021", "field": "school_min_l_student_day", "role": "minimum_for_school_not_kindergarten"}]
            elif rate == "resident_trips_day":
                record["reference_anchors"] = [{"source_id": "jica_his", "field": "gross_person_trips_day_2013", "role": "citywide_denominator_not_gate_rate"}]
            elif rate == "energy_kwh_m2_day" and use == "office":
                record["reference_anchors"] = [{"source_id": "office_hcmc_2015", "field": "electricity_kwh_m2_year", "role": "annual_office_comparator"}]
                # Only use source-backed status when the saved registry says the
                # number was actually adopted; never relabel an old run's .14.
                old = existing.get(path, {})
                if old.get("numeric_source"):
                    record.update({key: deepcopy(old[key]) for key in
                                   ("numeric_source", "kind", "value_status", "geography", "data_year", "default_reason")})
            result[path] = record
    for path, (group, unit, denominator, minimum, maximum) in GLOBALS.items():
        if path not in library:
            continue
        old = existing.get(path, {})
        record = {**deepcopy(old), "parameter_id": path, "value": library[path], "group": group,
                  "unit": unit, "denominator": denominator, "checked_at": CHECKED_AT,
                  "kind": old.get("kind", "synthetic"), "value_status": "reviewed_but_unsourced_default",
                  "numeric_source": None, "geography": "Uncalibrated pilot assumption", "data_year": None,
                  "needs_local_calibration": True, "hard_bounds": [minimum, maximum],
                  "reference_anchors": [], "default_reason": "Scenario assumption; no local numeric observation verified."}
        if path == "return_fraction":
            record["reference_anchors"] = [{"source_id": "qcvn01_2021", "field": "sanitary_planning_min_fraction", "role": "planning_lower_bound_not_measured_indoor_return"}]
        if old.get("kind") == "population_based_estimate":
            record.update(value_status="population_based_uncalibrated_estimate", default_reason=old.get("assumptions", "Population-derived prior"))
        result[path] = record
    return result


def install(library, profile):
    """Apply a compatible local historical office proxy; audit every demand rate."""
    library["coefficient_profile"] = profile
    for rates in library["uses"].values():
        rates["staff_trips_day"] = 2
    library["reuse_treatment_kwh_m3"] = .6
    if profile == "reviewed":
        library["uses"]["office"]["energy_kwh_m2_day"] = 116.4/365
        library["parameter_provenance"]["uses.office.energy_kwh_m2_day"] = {
            "kind": "estimated", "value_status": "historical_local_benchmark_adapted",
            "numeric_source": {"source_id": "office_hcmc_2015", "original_value": 116.4,
                               "original_unit": "kWh/m2_floor/year", "conversion": "original_value / 365"},
            "geography": "HCMC historical office sample used as a pilot proxy", "data_year": 2015,
            "default_reason": "Same use and floor-area denominator; annual average converted to calendar-day EUI. Not calibrated to this site or its peak."}
        library["kind"] = "mixed_references_and_synthetic"
        library["source"] = "Reviewed historical office EUI plus explicitly unverified demand and infrastructure assumptions"
    records = entries(library)
    library["parameter_provenance"].update(records)
    library["coefficient_sources"] = reviewed_sources()
    library["coefficient_catalog_version"] = VERSION
    library["parameter_validation"].update(
        demand_catalog_reviewed=True, all_demand_defaults_sourced=False,
        source_backed_demand_defaults=sum(bool(r["numeric_source"]) for r in records.values()),
        unsourced_demand_defaults=sum(not r["numeric_source"] for r in records.values()))


def catalog(library):
    records = entries(library)
    sources = deepcopy(library.get("coefficient_sources", reviewed_sources()))
    for source in sources.values():
        source["review_due"] = bool(source.get("valid_until") and date.today().isoformat() > source["valid_until"])
    return {"version": library.get("coefficient_catalog_version", VERSION), "library_version": library["version"],
            "profile": library.get("coefficient_profile", "legacy_frozen"), "parameters": records,
            "sources": sources, "local_calibration": False,
            "note": "Sources for comparator values are checked; source minima, foreign aggregates and citywide trips are not automatically applied building coefficients. Sensitivity ranges are scenarios, not confidence intervals."}
