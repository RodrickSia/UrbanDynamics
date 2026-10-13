"""Demo assumptions, deliberately labelled synthetic rather than local observations."""
from copy import deepcopy

VERSION = "thu-duc-demo-library-1.3"
SOURCE = "Synthetic hackathon scenario; not calibrated or a Vietnamese regulatory standard"

USES = {
    "residential": {"water_l_person_day": 120, "visitor_l_day": 15, "staff_l_day": 40,
                    "energy_kwh_m2_day": .11, "resident_trips_day": 2, "visitor_trips_day": 2},
    "school": {"water_l_person_day": 100, "visitor_l_day": 25, "staff_l_day": 40,
               "energy_kwh_m2_day": .07, "resident_trips_day": 2, "visitor_trips_day": 2},
    "office": {"water_l_person_day": 100, "visitor_l_day": 15, "staff_l_day": 45,
               "energy_kwh_m2_day": .14, "resident_trips_day": 2, "visitor_trips_day": 2},
    "hospital": {"water_l_person_day": 180, "visitor_l_day": 40, "staff_l_day": 60,
                 "energy_kwh_m2_day": .22, "resident_trips_day": 1, "visitor_trips_day": 2},
    "other": {"water_l_person_day": 120, "visitor_l_day": 20, "staff_l_day": 40,
              "energy_kwh_m2_day": .10, "resident_trips_day": 2, "visitor_trips_day": 2},
}
for use, rates in USES.items():
    rates["user_l_day"] = {"residential": 40, "school": 25, "office": 45, "hospital": 180, "other": 40}[use]
    rates["user_trips_day"] = 1 if use == "hospital" else 2
PROFILE_RESIDENT = [1, .7, .6, .6, .8, 1.8, 4, 6, 4, 2, 2, 3, 4, 3, 2, 2, 3, 5, 7, 7, 6, 4, 2, 1.5]
PROFILE_DAY = [.2, .2, .2, .2, .2, .5, 1, 4, 7, 6, 5, 5, 4, 5, 5, 5, 6, 7, 3, 1, .5, .3, .2, .2]


def normalized(values):
    return [value / sum(values) for value in values]


def parameters(level, coefficient_profile="reviewed"):
    factor = {"low": .7, "base": 1, "high": 1.3}[level]
    library = {
        "version": VERSION, "kind": "synthetic", "source": SOURCE,
        "uses": deepcopy(USES), "runoff_coefficients": {"roof": .9, "paved": .85, "permeable": .35, "green": .2},
        "return_fraction": .8, "efficient_fixture_factor": .75, "efficient_equipment_factor": .8,
        "irrigation_l_m2_day": 2, "ev_kw": 7, "ev_hours": 4,
        "car_person_share": .25, "car_occupancy": 1.6, "motorcycle_person_share": .55,
        "motorcycle_occupancy": 1.2, "scenario_load_factor": factor,
        "rainfall_mm": 60 * factor, "background_vehicles_hour": round(400 * factor),
        "drain_diameter_m": .3, "drain_slope": .01, "drain_manning_n": .013,
        "water_spare_m3_day": 60, "wastewater_spare_m3_day": 45, "power_spare_kw": 200,
        "service_capacity_people": 1500, "existing_service_users": 1200,
        "goals": {"green_min_percent": 20, "impervious_max_percent": 70, "runoff_increase_max_percent": 10},
        "costs_vnd": {"green_m2": 150000, "permeable_m2": 200000, "storage_m3": 3000000,
                      "fixtures_person": 600000, "equipment_m2": 150000, "gate_lane": 200000000,
                      "schedule": 5000000},
        "profiles": {"residential": normalized(PROFILE_RESIDENT), "day": normalized(PROFILE_DAY)},
        "units": {"water_l_person_day": "L/person/day", "energy_kwh_m2_day": "kWh/m2/day",
                  "background_vehicles_hour": "vehicles/hour", "rainfall_mm": "mm/event",
                  "power_spare_kw": "kW", "water_spare_m3_day": "m3/day"},
        "scenario_definition": "low/base/high jointly vary rain and travel demand; stress scenarios, not probabilities",
        "swmm": {"horton_max_mm_hour": 60, "horton_min_mm_hour": 6, "horton_decay_per_hour": 4,
                 "dry_days": 7, "impervious_manning_n": .015, "pervious_manning_n": .15,
                 "impervious_depression_mm": 1.5, "pervious_depression_mm": 5,
                 "zero_depression_percent": 25, "permeable_impervious_percent": 30,
                 "surface_slope_percent": 1, "orifice_discharge_coefficient": .65},
    }
    units = {"return_fraction": "fraction", "efficient_fixture_factor": "multiplier", "efficient_equipment_factor": "multiplier",
             "irrigation_l_m2_day": "L/m2/day", "ev_kw": "kW/charger", "ev_hours": "hours/day",
             "car_person_share": "fraction", "car_occupancy": "people/car", "motorcycle_person_share": "fraction",
             "motorcycle_occupancy": "people/motorcycle", "scenario_load_factor": "multiplier",
             "drain_diameter_m": "m", "drain_slope": "m/m", "drain_manning_n": "s/m^(1/3)",
             "wastewater_spare_m3_day": "m3/day", "service_capacity_people": "people/day", "existing_service_users": "people/day"}
    library["units"].update(units)
    library["parameter_provenance"] = {k: {"kind": "synthetic", "source": SOURCE, "version": VERSION,
                                            "unit": library["units"].get(k, "see parameter name / group")}
                                        for k, v in library.items() if isinstance(v, (int, float))}
    # References describe methods, not validation of our numerical defaults.
    references = {
        "water": {"url": "https://congbao.chinhphu.vn/van-ban/thong-tu-so-01-2021-tt-bxd-33751.htm",
                  "title": "QCVN 01:2021/BXD published by Government Gazette", "use": "Planning reference to review; default rates are not claimed to be extracted regulatory values"},
        "energy": {"url": "https://www.energy.gov/cmei/buildings/commercial-reference-buildings",
                   "title": "DOE Commercial Reference Buildings", "use": "Archetype method; US climate/buildings are not calibrated Vietnamese demand"},
        "drainage": {"url": "https://www.epa.gov/water-research/storm-water-management-model-swmm",
                     "title": "EPA SWMM", "use": "Hydrological/hydraulic method, not local coefficients or observed sewers"},
        "traffic": {"url": "https://sumo.dlr.de/docs/Networks/Import/OpenStreetMap.html",
                    "title": "SUMO OSM network import", "use": "Topology import; not observed OD, traffic volume or signal timing"},
    }
    library["references"] = references
    def register(prefix, values, unit, reference):
        for key, value in values.items():
            if isinstance(value, dict):
                register(f"{prefix}{key}.", value, unit, reference)
            elif isinstance(value, (int, float, list)):
                library["parameter_provenance"][f"{prefix}{key}"] = {
                    "kind": "synthetic", "value_status": "unvalidated_scenario_default", "source": SOURCE,
                    "unit": unit.get(key, "see field definition"), "version": VERSION,
                    "method_reference": reference, "numeric_source": None,
                    "needs_local_calibration": True}
    register("uses.", library["uses"], {"water_l_person_day": "L/person/day", "visitor_l_day": "L/visit",
             "staff_l_day": "L/person/day", "user_l_day": "L/user/day", "energy_kwh_m2_day": "kWh/m2/day",
             "resident_trips_day": "trips/person/day", "visitor_trips_day": "trips/visit", "user_trips_day": "trips/user/day"}, "water/energy/traffic")
    register("runoff_coefficients.", library["runoff_coefficients"], {}, "drainage")
    register("swmm.", library["swmm"], {}, "drainage")
    register("profiles.", library["profiles"], {}, "water/energy/traffic")
    register("costs_vnd.", library["costs_vnd"], {}, None)
    library["parameter_validation"] = {"local_calibration": False, "numeric_defaults_verified_from_references": False,
                                       "note": "Method references do not make scenario rates measured data, legal compliance or a quoted price."}
    from .parameter_catalog import install
    install(library, coefficient_profile)
    return library
