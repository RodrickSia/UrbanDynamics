"""Utility capacity is shared once per zone; peak of summed profiles."""
from .models import UtilityZone


def aggregate(zones: list[UtilityZone], parcel_loads, *, unknown_occupancy=False):
    output = []
    for zone in sorted(zones, key=lambda z: z.id):
        loads = [item["demand"] for item in parcel_loads if item["utility_zone_id"] == zone.id]
        power = [zone.background_power_kw[h]+sum(d["hourly"]["power_kw"][h] for d in loads) for h in range(24)]
        water = zone.background_freshwater_m3_day+sum(d["freshwater_m3_day"] for d in loads)
        waste = zone.background_wastewater_m3_day+sum(d["wastewater_m3_day"] for d in loads)
        metrics = {"power_peak_kw": max(power), "freshwater_m3_day": water, "wastewater_m3_day": waste}
        limits = {"power_peak_kw": zone.power_capacity_kw, "freshwater_m3_day": zone.water_capacity_m3_day,
                  "wastewater_m3_day": zone.wastewater_capacity_m3_day}
        checks = []
        for metric, value in metrics.items():
            limit = limits[metric]
            status = "unknown" if limit is None or unknown_occupancy or zone.source_kind == "unknown" else "within_capacity" if value <= limit else "exceeds_capacity"
            checks.append({"metric": metric, "value": value, "capacity": limit, "status": status,
                           "source_kind": zone.source_kind, "source": zone.source,
                           "remaining_capacity": limit-value if limit is not None and status != "unknown" else None})
        output.append({"id": zone.id, "metrics": metrics, "hourly_power_kw": power, "checks": checks,
                       "background_basis": "Background excludes all registered parcels; selected parcel loads added once."})
    return output
