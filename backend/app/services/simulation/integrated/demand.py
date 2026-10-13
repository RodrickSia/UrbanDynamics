"""One set of people and hourly schedules supplies all demand modules."""
from .library import normalized


def smooth(profile, hours):
    return [sum(profile[(i-j) % 24] for j in range(hours))/hours for i in range(24)]


def calculate(design, floor_areas, library):
    water = [0.0]*24
    waste = [0.0]*24
    power = [0.0]*24
    trips = [0.0]*24
    residents = staff = visitors = users = capacity = 0
    fixture_factor = library["efficient_fixture_factor"] if design.efficient_fixtures else 1
    equipment_factor = library["efficient_equipment_factor"] if design.efficient_equipment else 1
    for block, floor_area in zip(design.buildings, floor_areas):
        rates = library["uses"][block.use]
        profile = normalized(block.activity_profile) if block.activity_profile else library["profiles"][
            "residential" if block.use in ("residential", "hospital") else "day"]
        profile = smooth(profile, design.stagger_hours)
        resident_profile = smooth(library["profiles"]["residential"], design.stagger_hours)
        residents += block.residents
        staff += block.staff
        visitors += block.daily_visitors
        users += block.daily_users
        capacity += block.service_capacity
        for hour in range(24):
            indoor_water = fixture_factor * (block.residents*rates["water_l_person_day"]*resident_profile[hour]
                            + (block.staff*rates["staff_l_day"]+block.daily_visitors*rates["visitor_l_day"]+block.daily_users*rates['user_l_day'])*profile[hour])/1000
            water[hour] += indoor_water
            waste[hour] += indoor_water*library["return_fraction"]
            # The normalized load curve already incorporates coincidence; no second diversity factor.
            power[hour] += floor_area*rates["energy_kwh_m2_day"]*profile[hour]*equipment_factor
            person_trips = block.residents*rates["resident_trips_day"]*resident_profile[hour] + (
                block.staff*rates.get("staff_trips_day", 2) + block.daily_visitors*rates["visitor_trips_day"]+block.daily_users*rates['user_trips_day'])*profile[hour]
            trips[hour] += person_trips*library["scenario_load_factor"]
    irrigation = design.green_m2*library["irrigation_l_m2_day"]/1000
    water[5] += irrigation  # Irrigation is excluded from sanitary wastewater.
    freshwater_before_reuse = sum(water)
    # Reuse is a design supply, not invented availability from today's rain event.
    # Limit to sanitary flow; the explicit external treatment/pump allowance is recorded below.
    reused = min(design.reuse_m3_day, sum(waste), sum(water))
    if freshwater_before_reuse:
        water = [v*(1-reused/freshwater_before_reuse) for v in water]
    waste_before_reuse = sum(waste)
    if waste_before_reuse:
        waste = [v*(1-reused/waste_before_reuse) for v in waste]
    for offset in range(library["ev_hours"]):
        power[(design.ev_charging_hour+offset) % 24] += design.ev_chargers*library["ev_kw"]
    power[5] += reused*library.get("reuse_treatment_kwh_m3", .6)
    cars = [v*library["car_person_share"]/library["car_occupancy"] for v in trips]
    bikes = [v*library["motorcycle_person_share"]/library["motorcycle_occupancy"] for v in trips]
    return {"residents": residents, "staff": staff, "daily_visitors": visitors, "daily_users": users, "service_capacity": capacity,
            "freshwater_m3_day": sum(water), "water_peak_m3_hour": max(water),
            "wastewater_m3_day": sum(waste), "wastewater_peak_m3_hour": max(waste),
            "energy_kwh_day": sum(power), "power_peak_kw": max(power),
            "reused_m3_day": reused, "irrigation_m3_day": irrigation,
            "person_trips_day": sum(trips), "car_trips_day": sum(cars), "motorcycle_trips_day": sum(bikes),
            "vehicle_peak_hour": max(a+b for a, b in zip(cars, bikes)),
            "hourly": {"hour_local": list(range(24)), "water_m3": water, "wastewater_m3": waste,
                       "power_kw": power, "person_trips": trips, "cars": cars, "motorcycles": bikes},
            "water_ledger": {"indoor_and_irrigation_m3": freshwater_before_reuse, "reuse_supply_m3": reused,
                             "freshwater_m3": sum(water), "sanitary_before_reuse_m3": waste_before_reuse,
                             "sanitary_discharge_m3": sum(waste)},
            "provenance": {"kind": library["kind"], "library_version": library["version"],
                           "coefficient_profile": library.get("coefficient_profile", "legacy_frozen"),
                           "local_calibration": False,
                           "reuse": "Assumed daily treated sanitary supply; needs treatment design validation"}}
