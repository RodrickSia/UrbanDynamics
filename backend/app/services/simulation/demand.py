"""Demand/capacity screening with planner-supplied factors, not traffic microsimulation."""

DEMAND_METRICS = {
    "peak_vehicle_trips_per_hour": ("Chuyến xe giờ cao điểm", "vehicle_trips/h", -1),
    "water_demand_m3_per_day": ("Nhu cầu nước", "m3/day", -1),
    "wastewater_m3_per_day": ("Nước thải", "m3/day", -1),
    "peak_power_kw": ("Nhu cầu điện giờ cao điểm", "kW", -1),
}
CAPACITY_FIELDS = {
    "peak_vehicle_trips_per_hour": "remaining_vehicle_trips_per_hour",
    "water_demand_m3_per_day": "remaining_water_m3_per_day",
    "wastewater_m3_per_day": "remaining_wastewater_m3_per_day",
    "peak_power_kw": "remaining_power_kw",
}


def demand_metrics(users, assumptions, operations=None):
    if assumptions is None:
        return {}
    operations = operations or {}
    share = operations.get("private_vehicle_share", assumptions.private_vehicle_share)
    water_saving = operations.get("water_saving_fraction", 0)
    power_saving = operations.get("power_saving_fraction", 0)
    water = users * assumptions.water_liters_per_user_day / 1000 * (1 - water_saving)
    return {
        "peak_vehicle_trips_per_hour": users * assumptions.peak_person_trips_per_user_hour * share / assumptions.average_vehicle_occupancy,
        "water_demand_m3_per_day": water,
        "wastewater_m3_per_day": water * assumptions.wastewater_fraction,
        "peak_power_kw": users * assumptions.peak_kw_per_user * (1 - power_saving),
    }


def operation_options(request, constraints, baseline, current):
    if request.demand is None:
        return [{"private_vehicle_share": None, "water_saving_fraction": 0, "power_saving_fraction": 0}]
    demand = request.demand
    share_options = {demand.private_vehicle_share}
    if constraints.transport_shift_feasible and current["peak_vehicle_trips_per_hour"] > 0:
        target = baseline["peak_vehicle_trips_per_hour"] + demand.remaining_vehicle_trips_per_hour
        needed_share = demand.private_vehicle_share * min(1, target / current["peak_vehicle_trips_per_hour"])
        share_options.add(min(demand.private_vehicle_share, max(constraints.minimum_private_vehicle_share, needed_share)))
    water_needed = 0
    for metric in ("water_demand_m3_per_day", "wastewater_m3_per_day"):
        if current[metric] > 0:
            target = baseline[metric] + getattr(demand, CAPACITY_FIELDS[metric])
            water_needed = max(water_needed, 1 - target / current[metric])
    power_needed = (max(0, 1 - (baseline["peak_power_kw"] + demand.remaining_power_kw) / current["peak_power_kw"])
                    if current["peak_power_kw"] > 0 else 0)
    water_options = {0, min(max(0, water_needed), constraints.maximum_water_saving_fraction)}
    power_options = {0, min(power_needed, constraints.maximum_power_saving_fraction)}
    return [{"private_vehicle_share": share, "water_saving_fraction": water, "power_saving_fraction": power}
            for share in sorted(share_options) for water in sorted(water_options) for power in sorted(power_options)]


def operation_cost(operations, request, constraints):
    if request.demand is None:
        return 0
    return (
        (request.demand.private_vehicle_share - operations["private_vehicle_share"]) * 100 * constraints.transport_cost_vnd_per_share_point
        + operations["water_saving_fraction"] * 100 * constraints.water_cost_vnd_per_saving_point
        + operations["power_saving_fraction"] * 100 * constraints.power_cost_vnd_per_saving_point
    )
