"""Explicit synthetic pilot; these parcels are examples, not surveyed sites."""
from copy import deepcopy

from ..engine import polygon_and_area
from ..models import PolygonInput


def rectangle(west, south, width=.001, height=.001):
    return {"type": "Polygon", "coordinates": [[[west, south], [west+width, south],
            [west+width, south+height], [west, south+height], [west, south]]]}


def single_site_study():
    payload = demo_study()
    payload["title"] = "Single-site residential pilot on shared regional context"
    payload["projects"] = payload["projects"][:1]
    payload["options"] = payload["options"][:1]
    return payload


def demo_study(mode="site_selection"):
    projects = []
    for identifier, west in zip(("A", "B", "C"), (106.758, 106.765, 106.771)):
        site = rectangle(west, 10.82)
        area = polygon_and_area(PolygonInput(**site))[1]
        footprint = rectangle(west+.0003, 10.8203, .0004, .0004)
        roof = polygon_and_area(PolygonInput(**footprint))[1]
        block = {"name": f"Project {identifier}", "use": "residential", "footprint": footprint,
                 "floors": 12, "height_m": 36, "gross_floor_area_m2": 24000,
                 "units": 200, "residents": 600, "staff": 12, "daily_visitors": 80}
        design = {"buildings": [block], "paved_m2": area*.7-roof, "green_m2": area*.2,
                  "permeable_m2": area*.1, "parking_spaces": 200, "ev_chargers": 12}
        if mode == "cumulative" and identifier == "B":
            block.update(use="school", floors=4, height_m=14, gross_floor_area_m2=8000,
                         units=0, residents=0, daily_users=600, staff=60, service_capacity=600)
            design.update(ev_chargers=0, parking_spaces=80)
        if mode == "cumulative" and identifier == "C":
            block.update(units=150, residents=450, gross_floor_area_m2=18000)
            design.update(ev_chargers=8, parking_spaces=150)
        projects.append({"id": identifier, "title": f"Khu đất {identifier} — fixture synthetic",
                         "site": site, "baseline": {"buildings": [], "paved_m2": area*.4,
                                                       "green_m2": area*.4, "permeable_m2": area*.2},
                         "baseline_source": "Synthetic unoccupied parcel, mixed green/paved/permeable surfaces; not a surveyed vacant site",
                         "baseline_kind": "synthetic", "baseline_occupancy": "estimated",
                         "development": design, "utility_zone_id": "shared", "catchment_id": "pilot"})
    single = [{"id": f"{p['id']}_only", "title": f"Chỉ triển khai {p['id']}", "active_project_ids": [p["id"]]} for p in projects]
    payload = {"schema_version": 1, "title": "So sánh A/B/C" if mode == "site_selection" else "Danh mục A+B+C",
               "mode": mode, "study_area": rectangle(106.755, 10.815, .02, .02),
               "source_note": "All pilot parcels, capacities, baseline occupancy and regional background are synthetic hackathon fixtures.",
               "data_mode": "synthetic", "projects": projects, "options": single,
               "school_age_fraction": .18, "school_max_walk_m": 1200,
               "background_school_groups": [
                   {"id": "west", "location": [106.759, 10.821], "students": 100,
                    "source": "Synthetic age-group distribution, counted once outside registered parcels"},
                   {"id": "east", "location": [106.769, 10.821], "students": 116,
                    "source": "Synthetic age-group distribution, counted once outside registered parcels"}],
               "school_facilities": [
                   {"id": "west_school", "location": [106.757, 10.821], "capacity_places": 230,
                    "reserved_places": 40, "source": "Synthetic 230-place school, 40 places reserved for students outside the modeled groups"}],
               "comparison_policy": "equal_program" if mode == "site_selection" else "declared_programs",
               "utility_zones": [{"id": "shared", "source_kind": "synthetic",
                    "source": "Shared synthetic supply zone. Background excludes all three parcels; capacities selected to exercise portfolio constraints.",
                    "background_power_kw": [80]*24, "background_freshwater_m3_day": 40,
                    "background_wastewater_m3_day": 30, "power_capacity_kw": 500,
                    "water_capacity_m3_day": 180, "wastewater_capacity_m3_day": 130}]}
    if mode == "site_selection":
        payload["program_targets"] = {"housing_units": 200, "residents": 600, "floor_area_m2": 24000}
    else:
        payload["options"] += [{"id": "AB", "title": "A và B", "active_project_ids": ["A", "B"]},
                               {"id": "ABC", "title": "Toàn danh mục", "active_project_ids": ["A", "B", "C"]}]
        payload["phases"] = [{"id": "phase_1", "sequence": 1, "title": "Giai đoạn 1", "active_project_ids": ["A"]},
                             {"id": "phase_2", "sequence": 2, "title": "Giai đoạn 2", "active_project_ids": ["A", "B"]},
                             {"id": "phase_3", "sequence": 3, "title": "Giai đoạn 3", "active_project_ids": ["A", "B", "C"]}]
    return deepcopy(payload)


def rehousing_study():
    payload = demo_study("cumulative")
    payload["title"] = "Di dời 100 cư dân A sang chung cư C — synthetic"
    origin, destination = payload["projects"][0], payload["projects"][2]
    empty = deepcopy(origin["baseline"])
    origin["baseline"] = deepcopy(origin["development"])
    origin["baseline"]["buildings"][0].update(name="Existing homes A", floors=4, height_m=12,
                                               gross_floor_area_m2=8000, units=40, residents=100,
                                               staff=2, daily_visitors=15)
    origin["baseline"].update(ev_chargers=0, parking_spaces=40)
    origin["baseline_occupancy"] = "known"
    origin["baseline_source"] = "Synthetic 40-unit existing housing with 100 residents; hypothetical rehousing case, not a survey"
    origin["development"] = empty
    origin["title"] = "A — giải phóng nhà ở hiện hữu sau tái định cư"
    destination["development"]["buildings"][0]["residents"] = 300
    destination["title"] = "C — 300 cư dân, bao gồm 100 người từ A"
    payload["options"].append({"id": "AC", "title": "A được thay thế, C tiếp nhận cư dân", "active_project_ids": ["A", "C"]})
    payload["phases"] = [
        {"id": "phase_1", "sequence": 1, "title": "C vận hành", "active_project_ids": ["C"]},
        {"id": "phase_2", "sequence": 2, "title": "Thay thế A và tái định cư sang C", "active_project_ids": ["A", "C"]},
        {"id": "phase_3", "sequence": 3, "title": "Thêm trường B", "active_project_ids": ["A", "B", "C"]}]
    payload["resident_transfers"] = [
        {"id": "A_to_C", "from_project_id": "A", "to_project_id": "C", "residents": 100,
         "when_active_project_ids": ["A", "C"],
         "source": "Synthetic rehousing declaration; 100 people are included in C's final 300 residents"},
        {"id": "outside_to_C", "from_project_id": None, "to_project_id": "C", "residents": 200,
         "when_active_project_ids": ["C"],
         "source": "Synthetic external inflow of 200 residents, already included in C's final 300 residents"}]
    payload["source_note"] += " Phase occupancy is a declared steady state, not a forecast of household moves or construction logistics."
    return payload


def inclusive_rehousing_study():
    """Synthetic snapshot deliberately includes A to demonstrate deduplication."""
    import math
    from .models import PlanningStudy
    from .context import build_context, canonical_numbers
    from .engine import evaluate
    from ..integrated.context import digest
    study = PlanningStudy(**rehousing_study())
    payload = study.model_dump(mode="json")
    baseline = evaluate(study, build_context(study), ())
    parcel = next(p for p in baseline["parcels"] if p["id"] == "A")
    loads = parcel["demand"]
    project = next(p for p in study.projects if p.id == "A")
    contribution = {"project_id": "A", "baseline_sha256": digest(canonical_numbers(project.baseline.model_dump(mode="json"))),
                    "source": "Synthetic parcel A totals included once in this regional snapshot; generated from the declared baseline and coefficient library",
                    "residents": 100,
                    "utilities": {"power_kw": loads["hourly"]["power_kw"], "freshwater_m3_day": loads["freshwater_m3_day"], "wastewater_m3_day": loads["wastewater_m3_day"]},
                    "traffic": {kind: [round(value) for value in loads["hourly"][kind]] for kind in ("cars", "motorcycles")},
                    "school_group_students": {"west": math.ceil(100*study.school_age_fraction)},
                    "drainage": {"area_m2": parcel["geometry"]["site_area_m2"], "impervious_m2": parcel["geometry"]["surfaces_m2"]["roof"]+parcel["geometry"]["surfaces_m2"]["paved"]}}
    payload["background_residents"] += contribution["residents"]
    zone = payload["utility_zones"][0]
    zone["background_power_kw"] = [a+b for a,b in zip(zone["background_power_kw"], contribution["utilities"]["power_kw"])]
    zone["background_freshwater_m3_day"] += contribution["utilities"]["freshwater_m3_day"]
    zone["background_wastewater_m3_day"] += contribution["utilities"]["wastewater_m3_day"]
    next(g for g in payload["background_school_groups"] if g["id"] == "west")["students"] += contribution["school_group_students"]["west"]
    catchment = payload["catchments"][0]
    impervious = catchment["background_area_m2"]*catchment["background_impervious_percent"]/100+contribution["drainage"]["impervious_m2"]
    catchment["background_area_m2"] += contribution["drainage"]["area_m2"]
    catchment["background_impervious_percent"] = impervious/catchment["background_area_m2"]*100
    payload["title"] = "Snapshot tổng vùng có chứa A — tự tách trước khi tính cộng dồn"
    payload["background_snapshot"] = {"id": "inclusive_rehousing_demo", "source": "Synthetic regional aggregates deliberately including existing parcel A; not sensor measurements",
                                      "included_modules": ["population", "utilities", "traffic", "school", "drainage"],
                                      "coverage": deepcopy(payload["study_area"]), "parcels": [contribution],
                                      "regional_traffic": {"cars": [100+v for v in contribution["traffic"]["cars"]], "motorcycles": [300+v for v in contribution["traffic"]["motorcycles"]]}}
    return payload
