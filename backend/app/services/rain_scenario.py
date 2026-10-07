import json

from shapely.geometry import shape
from src.pipelines.flood_risk.risk_assessment import evaluate

from app import repository


def run(rain_mm, radius_m, polygon=None):
    floods = repository.features("flood_history", limit=10000)
    if floods["metadata"]["truncated"]:
        raise ValueError("Too many historical observations for scenario")
    if polygon:
        area = shape(polygon)
        if area.is_empty or not area.is_valid or area.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Scenario area must be a valid polygon")
        if not (
            -180 <= area.bounds[0] < area.bounds[2] <= 180
            and -90 <= area.bounds[1] < area.bounds[3] <= 90
        ):
            raise ValueError("Scenario area must use WGS84")
        floods["features"] = [f for f in floods["features"] if area.covers(shape(f["geometry"]))]
    from src.pipelines.rainwater.load import input_pair
    forecast,history = input_pair(repository.directory())
    return {"type": "FeatureCollection", "features": evaluate(floods, forecast, history, rain_mm, radius_m),
            "metadata": {"scenario": True, "rain_3h_mm": rain_mm, "radius_m": radius_m,
                         "limitations": "Hypothetical rainfall indicator; not hydraulic flood simulation."}}
