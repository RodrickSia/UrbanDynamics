"""Event-volume screening; deliberately makes no hydraulic or flood-depth claim."""
import hashlib
import json
import math

from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.geometry.polygon import orient

from .models import BuildingScenario, BuildingPrediction, PolygonInput

MODEL_VERSION = "building-screening-1.0.0"
GEOD = Geod(ellps="WGS84")
LABELS = {
    "baseline": "Hiện trạng",
    "development": "Xây theo thiết kế ban đầu",
    "mitigated": "Xây có giải pháp cải thiện",
}
SURFACES = ("roof", "paved", "permeable", "green")
LIMITATIONS = [
    "Ước tính thể tích nước theo trận mưa đồng đều; chưa hiệu chỉnh với quan trắc.",
    "Hệ số dòng chảy và hiện trạng bề mặt do người dùng cung cấp; không tự suy ra từ vệ tinh.",
    "Không tính cường độ mưa theo thời gian, thấm động, mạng cống, địa hình hay triều.",
    "Giữ nước là phép trừ dung tích trống giả định, chưa mô hình hóa đường dẫn nước, bơm hay xả.",
    "Kết quả không dự báo độ sâu, vị trí, thời gian ngập hoặc tác động ngập đến khu lân cận.",
    "Chưa mô phỏng bóng đổ, nhiệt, giao thông, tiếp cận dịch vụ hoặc nhu cầu điện/nước.",
    "Số người và số tầng là thông số thiết kế; diện tích sàn là roof_m2 × floors, chưa kiểm tra pháp lý.",
]


def polygon_and_area(value: PolygonInput, *, maximum_area_m2=1_000_000):
    rings = value.coordinates
    if sum(map(len, rings)) > 500:
        raise ValueError("Polygon supports at most 500 vertices")
    for ring in rings:
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("Polygon rings must be closed and have at least four coordinates")
        if any(not (math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -85 <= y <= 85)
               for x, y in ring):
            raise ValueError("Coordinates must be finite WGS84 longitude/latitude")
    polygon = shape(value.model_dump())
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Polygon must be non-empty and valid, without self intersections")
    west, south, east, north = polygon.bounds
    if east - west > 0.1 or north - south > 0.1:
        raise ValueError("Use a local site, not a regional or antimeridian polygon")
    area = abs(GEOD.geometry_area_perimeter(orient(polygon, sign=1))[0])
    if not 1 <= area <= maximum_area_m2:
        raise ValueError(f"Site or footprint must cover between 1 and {maximum_area_m2:,} m2")
    return polygon, area


def variant_metrics(variant, rainfall_mm, coefficients, site_area):
    surfaces = {s: getattr(variant, f"{s}_m2") for s in SURFACES}
    contributions = {s: rainfall_mm / 1000 * area * getattr(coefficients, s)
                     for s, area in surfaces.items()}
    gross = sum(contributions.values())
    retained = min(gross, variant.available_storage_m3)
    return {
        "surfaces_m2": surfaces, "surface_area_residual_m2": sum(surfaces.values()) - site_area,
        "rainfall_volume_m3": rainfall_mm / 1000 * site_area,
        "gross_runoff_m3": gross, "retained_m3": retained, "unretained_runoff_m3": gross - retained,
        "unused_storage_m3": variant.available_storage_m3 - retained,
        "runoff_contributions_m3": contributions,
        "impervious_area_m2": variant.roof_m2 + variant.paved_m2,
        "green_area_m2": variant.green_m2,
        "gross_floor_area_estimate_m2": variant.roof_m2 * variant.floors,
        "users": variant.users,
    }


def calculate(request: BuildingScenario | BuildingPrediction) -> dict:
    site, site_area = polygon_and_area(request.site)
    # Tolerance only handles coordinate/measurement rounding, never normalizes inputs.
    tolerance = max(0.1, site_area * 0.0001)
    variants = {}
    features = [{"type": "Feature", "geometry": mapping(site),
                 "properties": {"role": "site", "area_m2": site_area}}]
    keys = list(LABELS) if isinstance(request, BuildingScenario) else ["baseline", "development"]
    for key in keys:
        variant = getattr(request, key)
        surfaces = {s: getattr(variant, f"{s}_m2") for s in SURFACES}
        if abs(sum(surfaces.values()) - site_area) > tolerance:
            raise ValueError(f"{key}: surface areas must sum to site area {site_area:.3f} m2 "
                             f"(tolerance {tolerance:.3f} m2)")
        if variant.footprint:
            footprint, footprint_area = polygon_and_area(variant.footprint)
            if not site.covers(footprint):
                raise ValueError(f"{key}: building footprint must be inside the site")
            if abs(footprint_area - variant.roof_m2) > tolerance:
                raise ValueError(f"{key}: roof_m2 must match footprint area {footprint_area:.3f} m2")
            features.append({"type": "Feature", "geometry": mapping(footprint),
                             "properties": {"role": "building", "variant": key}})
        variants[key] = {"label": LABELS[key], **variant_metrics(variant, request.rainfall_mm,
                                                             request.coefficients, site_area)}
    metrics = ("gross_runoff_m3", "unretained_runoff_m3", "impervious_area_m2",
               "green_area_m2", "gross_floor_area_estimate_m2", "users")
    comparisons = []
    pairs = [("baseline", "development")]
    if "mitigated" in variants:
        pairs.extend([("baseline", "mitigated"), ("development", "mitigated")])
    for before, after in pairs:
        delta = {m: variants[after][m] - variants[before][m] for m in metrics}
        previous = variants[before]["unretained_runoff_m3"]
        comparisons.append({"from": before, "to": after, "delta": delta,
                            "unretained_runoff_change_pct":
                                100 * delta["unretained_runoff_m3"] / previous if previous else None})
    inputs = request.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return {
        "model_version": MODEL_VERSION, "input_sha256": digest,
        "assessment_level": "uncalibrated_screening", "site_area_m2": site_area,
        "inputs": inputs, "variants": variants, "comparisons": comparisons,
        "map": {"type": "FeatureCollection", "features": features},
        "method": {
            "runoff": "V = rainfall_mm / 1000 × Σ(area_m2 × coefficient)",
            "storage": "retained = min(gross_runoff, available_storage); unretained = gross - retained",
            "area": "WGS84 ellipsoidal polygon area (pyproj.Geod); holes excluded",
            "coefficient_basis": request.coefficient_basis,
            "design_basis": request.design_basis,
            "units": {"area": "m2", "volume": "m3", "rainfall": "mm"},
            "area_tolerance_m2": tolerance,
        },
        "limitations": LIMITATIONS,
        "unavailable_modules": ["flood_depth", "neighbourhood_flood_impact", "shadow",
                                "thermal_comfort", "traffic", "service_access", "utility_demand"],
    }
