"""Explicitly synthetic three-option example; never represents a surveyed parcel."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.simulation.engine import polygon_and_area
from app.services.simulation.models import PolygonInput


def sample_payload():
    site = {"type": "Polygon", "coordinates": [
        [[106.76,10.82],[106.761,10.82],[106.761,10.821],[106.76,10.821],[106.76,10.82]]
    ]}
    _, area = polygon_and_area(PolygonInput(**site))
    def variant(shares, storage=0, floors=3, users=600):
        return {**{f"{name}_m2": area * ratio for name, ratio in
                   zip(("roof", "paved", "permeable", "green"), shares)},
                "available_storage_m3": storage, "floors": floors, "users": users}
    return {
        "title": "Ví dụ giả định · xây trường học", "building_use": "school", "site": site,
        "rainfall_mm": 60, "coefficients": {"roof": .9, "paved": .85, "permeable": .35, "green": .2},
        "coefficient_basis": "Hệ số minh họa do người dùng giả định; chưa hiệu chỉnh cho Thủ Đức.",
        "design_basis": "Hình học và thiết kế giả định; chưa khảo sát hiện trạng hoặc quyền xây dựng.",
        "baseline": variant([0, .1, .2, .7], floors=1, users=0),
        "development": variant([.3, .5, .1, .1]),
        "mitigated": variant([.3, .2, .2, .3], storage=80),
    }


def prediction_payload():
    payload = sample_payload()
    del payload["mitigated"]
    payload["evaluation"] = {"allowed_runoff_increase_pct": 0, "minimum_green_pct": 30,
                             "maximum_impervious_pct": 70, "basis": "Mục tiêu giả định cho thử nghiệm phần mềm."}
    payload["demand"] = {
        "peak_person_trips_per_user_hour": .25, "private_vehicle_share": .8, "average_vehicle_occupancy": 1.5,
        "water_liters_per_user_day": 80, "wastewater_fraction": .8, "peak_kw_per_user": .1,
        "remaining_vehicle_trips_per_hour": 60, "remaining_water_m3_per_day": 30,
        "remaining_wastewater_m3_per_day": 25, "remaining_power_kw": 45,
        "basis": "Hệ số nhu cầu và công suất giả định; chưa có khảo sát hạ tầng thực tế.",
    }
    return payload


def improvement_constraints(area):
    return {
        "minimum_paved_m2": .1 * area, "maximum_green_conversion_m2": .2 * area,
        "maximum_permeable_conversion_m2": .3 * area, "maximum_additional_storage_m3": 100,
        "budget_vnd": 1_000_000_000, "green_cost_vnd_per_m2": 100_000,
        "permeable_cost_vnd_per_m2": 150_000, "storage_cost_vnd_per_m3": 2_000_000,
        "minimum_private_vehicle_share": .4, "transport_shift_feasible": True,
        "maximum_water_saving_fraction": .4, "maximum_power_saving_fraction": .3,
        "transport_cost_vnd_per_share_point": 2_000_000, "water_cost_vnd_per_saving_point": 1_000_000,
        "power_cost_vnd_per_saving_point": 1_500_000,
        "cost_basis": "Giới hạn và chi phí giả định để thử phần mềm; chưa xác nhận báo giá hoặc khả thi thực tế.",
    }
