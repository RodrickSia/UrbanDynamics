"""Predict impacts first, then search bounded design changes using the same engine.

No learned flood, heat or traffic model is claimed. Targets and costs are supplied
by the planner. Recommendations preserve the building and its service capacity.
"""
import hashlib
import json

from .engine import calculate, variant_metrics
from .models import BuildingPrediction, ImprovementConstraints
from .demand import CAPACITY_FIELDS, DEMAND_METRICS, demand_metrics, operation_cost, operation_options

VERSION = "building-impact-2.0.0"
METRICS = {
    "unretained_runoff_m3": ("Nước còn lại sau giữ nước", "m3", -1),
    "green_area_m2": ("Diện tích đất xanh", "m2", 1),
    "impervious_area_m2": ("Mái và sân cứng", "m2", -1),
}


def direction(before, after, sign):
    delta = after - before
    epsilon = max(1e-7, abs(before) * 1e-9)
    return "unchanged" if abs(delta) <= epsilon else "better" if delta * sign > 0 else "worse"


def assessment(baseline, proposed, targets, site_area, demand=None):
    metrics = {**METRICS, **(DEMAND_METRICS if demand else {})}
    changes = [{"metric": key, "label": label, "units": units,
                "baseline": baseline[key], "predicted": proposed[key],
                "delta": proposed[key] - baseline[key],
                "direction": direction(baseline[key], proposed[key], sign)}
               for key, (label, units, sign) in metrics.items()]
    directions = {item["direction"] for item in changes} - {"unchanged"}
    verdict = "mixed" if len(directions) == 2 else next(iter(directions)) if directions else "unchanged"
    limits = {
        "unretained_runoff_m3": baseline["unretained_runoff_m3"] * (1 + targets.allowed_runoff_increase_pct / 100),
        "green_area_m2": site_area * targets.minimum_green_pct / 100,
        "impervious_area_m2": site_area * targets.maximum_impervious_pct / 100,
    }
    if demand:
        limits.update({key: baseline[key] + getattr(demand, field) for key, field in CAPACITY_FIELDS.items()})
    checks = []
    for key, limit in limits.items():
        sign = metrics[key][2]
        margin = (proposed[key] - limit) * sign
        checks.append({"metric": key, "target": limit, "actual": proposed[key],
                       "operator": ">=" if sign > 0 else "<=", "met": margin >= -1e-7,
                       "shortfall": max(0, -margin),
                       **({"additional_demand": max(0, proposed[key] - baseline[key]),
                           "remaining_capacity": getattr(demand, CAPACITY_FIELDS[key])} if key in CAPACITY_FIELDS and demand else {})})
    return {"verdict": verdict, "changes": changes, "targets": checks,
            "targets_met": all(item["met"] for item in checks), "target_basis": targets.basis,
            "scope": "runoff_land_cover_and_demand_capacity" if demand else "runoff_volume_and_land_cover_only",
            "interpretation": "Tốt/xấu xét áp lực môi trường/hạ tầng theo giả định, chưa đánh giá lợi ích phục vụ, giá trị tổng thể hoặc tính hợp pháp của công trình."}


def predict(request: BuildingPrediction):
    result = calculate(request)
    result["model_version"] = VERSION
    result["workflow"] = "predict_assess_recommend"
    for key in result["variants"]:
        result["variants"][key].update(demand_metrics(getattr(request, key).users, request.demand))
    result["impact_assessment"] = assessment(result["variants"]["baseline"], result["variants"]["development"],
                                             request.evaluation, result["site_area_m2"], request.demand)
    if request.demand:
        result["unavailable_modules"] = [x for x in result["unavailable_modules"] if x not in ("utility_demand", "traffic")]
        result["unavailable_modules"].extend(["traffic_queues_and_travel_time", "network_utility_simulation"])
        result["limitations"] = [x for x in result["limitations"] if "nhu cầu điện/nước" not in x]
        result["limitations"].extend([
            "Giao thông là ước tính nhu cầu chuyến xe, chưa mô phỏng ùn tắc, hàng chờ hoặc thời gian đi lại.",
            "Nhu cầu và công suất còn lại do planner cung cấp; công suất phải là phần còn trống trước khi xây, không phải tổng công suất mạng.",
            "Tiết kiệm nước/điện và giảm tỷ lệ xe cá nhân là hiệu quả giả định cần kiểm chứng. Giảm nước thải theo hệ số đã nhập, chưa mô hình hóa tái sử dụng nước.",
            "Chưa mô phỏng bóng đổ, nhiệt, tiếp cận dịch vụ hoặc thủy lực/công suất thực tế của mạng cấp thoát nước và điện.",
        ])
        result["method"]["demand"] = {
            "traffic": "users × peak_person_trips_per_user_hour × private_vehicle_share / average_vehicle_occupancy",
            "water": "users × water_liters_per_user_day / 1000 × (1 - water_saving_fraction)",
            "wastewater": "water_demand × wastewater_fraction",
            "power": "users × peak_kw_per_user × (1 - power_saving_fraction)",
            "capacity": "max(0, proposed_demand - baseline_demand) compared with remaining capacity before development",
            "basis": request.demand.basis,
        }
    result["recommendations"] = []
    result["recommendation_status"] = "not_requested"
    return result


def recommend(source: dict, constraints: ImprovementConstraints):
    request = BuildingPrediction(**source["inputs"])
    result = predict(request)
    area = result["site_area_m2"]
    original = request.development
    current = result["variants"]["development"]
    baseline = result["variants"]["baseline"]
    if request.demand:
        required_costs = []
        if constraints.transport_shift_feasible and constraints.minimum_private_vehicle_share < request.demand.private_vehicle_share:
            required_costs.append("transport_cost_vnd_per_share_point")
        if constraints.maximum_water_saving_fraction > 0:
            required_costs.append("water_cost_vnd_per_saving_point")
        if constraints.maximum_power_saving_fraction > 0:
            required_costs.append("power_cost_vnd_per_saving_point")
        if any(field not in constraints.model_fields_set for field in required_costs):
            raise ValueError("Explicit operational intervention costs are required when enabling transport/water/power improvements")
    if constraints.minimum_paved_m2 > original.paved_m2 + 1e-7:
        raise ValueError("Minimum paved area cannot exceed the proposed paved area")
    convertible = max(0, original.paved_m2 - constraints.minimum_paved_m2)
    green_cap = min(convertible, constraints.maximum_green_conversion_m2)
    permeable_cap = min(convertible, constraints.maximum_permeable_conversion_m2)
    fractions = (0, .25, .5, .75, 1)
    candidates = []
    tried = 0
    seen = set()
    operations = operation_options(request, constraints, baseline, current)
    all_metrics = {**METRICS, **(DEMAND_METRICS if request.demand else {})}
    runoff_target = baseline["unretained_runoff_m3"] * (1 + request.evaluation.allowed_runoff_increase_pct / 100)
    for green_fraction in fractions:
        for permeable_fraction in fractions:
            green = green_cap * green_fraction
            permeable = permeable_cap * permeable_fraction
            if green + permeable > convertible + 1e-7:
                continue
            converted = original.model_copy(update={
                "paved_m2": max(0, original.paved_m2 - green - permeable),
                "green_m2": original.green_m2 + green,
                "permeable_m2": original.permeable_m2 + permeable,
            })
            preliminary = variant_metrics(converted, request.rainfall_mm, request.coefficients, area)
            needed = max(0, preliminary["unretained_runoff_m3"] - runoff_target)
            surface_cost = green * constraints.green_cost_vnd_per_m2 + permeable * constraints.permeable_cost_vnd_per_m2
            combinations = []
            for operation in operations:
                operating_cost = operation_cost(operation, request, constraints)
                if surface_cost + operating_cost > constraints.budget_vnd + 1e-5:
                    continue
                budget_storage_cap = max(0, constraints.budget_vnd - surface_cost - operating_cost) / constraints.storage_cost_vnd_per_m3
                storage_cap = min(constraints.maximum_additional_storage_m3, budget_storage_cap,
                                  1_000_000 - original.available_storage_m3)
                storages = {storage_cap * f for f in fractions} | {min(needed, storage_cap)}
                combinations.extend((s, operation, operating_cost) for s in sorted(storages))
            for storage, operation, operating_cost in combinations:
                tried += 1
                cost = surface_cost + storage * constraints.storage_cost_vnd_per_m3 + operating_cost
                if cost > constraints.budget_vnd + 1e-5:
                    continue
                identity = (round(green, 6), round(permeable, 6), round(storage, 6), *operation.values())
                if identity in seen:
                    continue
                seen.add(identity)
                design = converted.model_copy(update={"available_storage_m3": original.available_storage_m3 + storage})
                metrics = variant_metrics(design, request.rainfall_mm, request.coefficients, area)
                metrics.update(demand_metrics(design.users, request.demand, operation))
                directions = {direction(current[key], metrics[key], sign) for key, (_, _, sign) in all_metrics.items()}
                if "worse" in directions or "better" not in directions:
                    continue
                evaluated = assessment(baseline, metrics, request.evaluation, area, request.demand)
                candidates.append({"design": design.model_dump(mode="json"), "predicted": metrics,
                    "estimated_cost_vnd": cost, "assessment": evaluated, "operations": operation,
                    "changes": {"paved_to_green_m2": green, "paved_to_permeable_m2": permeable,
                                "additional_storage_m3": storage},
                    "delta_from_development": {key: metrics[key] - current[key] for key in all_metrics},
                    "remaining_failures": [item["metric"] for item in evaluated["targets"] if not item["met"]]})
    # Targets first; cheapest satisfactory candidate. If impossible, prioritize the
    # number of targets met, then the selected runoff target's shortfall, then cost.
    def rank(item):
        checks = item["assessment"]["targets"]
        failures = sum(not x["met"] for x in checks)
        return (failures, 0 if checks[0]["met"] else checks[0]["shortfall"], item["estimated_cost_vnd"],
                -item["predicted"]["green_area_m2"], item["predicted"]["impervious_area_m2"])
    candidates.sort(key=rank)
    chosen = candidates[:3]
    for index, candidate in enumerate(chosen, 1):
        candidate["id"] = f"suggestion-{index}"
        candidate["label"] = f"Gợi ý {index}"
    result["recommendations"] = chosen
    result["recommendation_status"] = ("targets_met" if chosen and chosen[0]["assessment"]["targets_met"]
                                       else "partial_improvement" if chosen else "no_feasible_improvement")
    result["recommendation_constraints"] = constraints.model_dump(mode="json")
    result["parent_run_id"] = source["id"]
    result["recommendation_method"] = {
        "version": "bounded-design-search-1.0.0", "evaluated_combinations": tried,
        "feasible_improving_candidates": len(candidates),
        "ranking": "Số mục tiêu môi trường/công suất chưa đạt → thiếu hụt mục tiêu dòng chảy → chi phí ước tính thấp nhất → đất xanh nhiều hơn.",
        "preserved": ["roof_m2", "footprint", "floors", "users"],
        "limitations": "Tìm kiếm hữu hạn: bước 25% bề mặt, dung tích mục tiêu và mức thay đổi vận hành cần để đạt công suất trong giới hạn. Chưa tối ưu toàn cục hoặc xác nhận vị trí cây/hồ, khả năng đổi phương tiện, hiệu quả tiết kiệm, báo giá và thi công.",
        "cost_basis": constraints.cost_basis,
    }
    digest = json.dumps({"input_sha256": result["input_sha256"], "constraints": result["recommendation_constraints"],
                         "method": result["recommendation_method"]["version"]}, sort_keys=True, ensure_ascii=False)
    result["recommendation_sha256"] = hashlib.sha256(digest.encode()).hexdigest()
    return result
