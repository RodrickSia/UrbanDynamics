import math

from shapely import affinity
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform, unary_union

from ..engine import polygon_and_area
from .context import projection


def analyze(site_input, design):
    site, area = polygon_and_area(site_input)
    forward, backward = projection(site)
    metric_site = transform(forward, site)
    footprints, floor_areas, heights = [], [], []
    for building in design.buildings:
        footprint, footprint_area = polygon_and_area(building.footprint)
        projected = transform(forward, footprint)
        # GEOS round trips can put a shared boundary a few nanometres outside.
        # Bound both distance (10 micrometres) and area (one square millimetre).
        if not site.covers(footprint) and not (metric_site.buffer(.00001).covers(projected)
                and projected.difference(metric_site).area <= .000001):
            raise ValueError("Every building footprint must lie inside the site")
        if any(projected.intersection(other).area > .01 for other in footprints):
            raise ValueError("Building footprints may not overlap")
        footprints.append(projected)
        floor_areas.append(building.gross_floor_area_m2 if building.gross_floor_area_m2 is not None else footprint_area*building.floors)
        heights.append(building.height_m)
    roof = sum(polygon_and_area(b.footprint)[1] for b in design.buildings)
    total = roof+design.paved_m2+design.permeable_m2+design.green_m2
    if abs(total-area) > max(.5, area*.0001):
        raise ValueError(f"Roof + paved + permeable + green must equal site area ({area:.3f} m2); got {total:.3f}")
    trees = []
    for tree in design.trees:
        point = Point(tree.longitude, tree.latitude)
        if not site.covers(point):
            raise ValueError("Tree location must be inside the site")
        trees.append(transform(forward, point).buffer(tree.canopy_radius_m))
    canopy = unary_union(trees).intersection(metric_site).area if trees else 0
    return {"site": site, "metric_site": metric_site, "forward": forward, "backward": backward,
            "footprints": footprints, "heights": heights, "trees": trees, "floor_areas": floor_areas,
            "metrics": {"site_area_m2": area, "roof_m2": roof, "floor_area_m2": sum(floor_areas),
                        "building_density_percent": roof/area*100, "far": sum(floor_areas)/area,
                        "green_percent": design.green_m2/area*100, "canopy_m2": canopy,
                        "impervious_percent": (roof+design.paved_m2)/area*100,
                        "surfaces_m2": {"roof": roof, "paved": design.paved_m2,
                                        "permeable": design.permeable_m2, "green": design.green_m2},
                        "floor_area_method": ["design" if b.gross_floor_area_m2 is not None else "footprint_times_floors_estimate"
                                              for b in design.buildings]}}


def solar_position(day, hour, lat, lon):
    # Approximate solar position, local UTC+7; suitable for geometric screening only.
    gamma = 2*math.pi/365*(day.timetuple().tm_yday-1+(hour-12)/24)
    declination = (.006918-.399912*math.cos(gamma)+.070257*math.sin(gamma)
                   -.006758*math.cos(2*gamma)+.000907*math.sin(2*gamma)
                   -.002697*math.cos(3*gamma)+.00148*math.sin(3*gamma))
    eq = 229.18*(.000075+.001868*math.cos(gamma)-.032077*math.sin(gamma)
                 -.014615*math.cos(2*gamma)-.040849*math.sin(2*gamma))
    hour_angle = math.radians((hour*60+eq+4*lon-420)/4-180)
    phi = math.radians(lat)
    east = -math.cos(declination)*math.sin(hour_angle)
    north = math.cos(phi)*math.sin(declination)-math.sin(phi)*math.cos(declination)*math.cos(hour_angle)
    up = math.sin(phi)*math.sin(declination)+math.cos(phi)*math.cos(declination)*math.cos(hour_angle)
    return east, north, up


def sweep(polygon, dx, dy):
    # Union of footprint, translated footprint and edge strips; preserves concave shape.
    pieces = [polygon, affinity.translate(polygon, dx, dy)]
    for ring in [polygon.exterior, *polygon.interiors]:
        points = list(ring.coords)
        for a, b in zip(points, points[1:]):
            strip = Polygon([a, b, (b[0]+dx, b[1]+dy), (a[0]+dx, a[1]+dy)])
            if strip.area > 1e-8:
                pieces.append(strip)
    return unary_union(pieces)


def shadows(geometry, design, conditions, surroundings=None):
    site = geometry["metric_site"]
    context_features = (surroundings or {}).get("features", [])
    context_objects = [(transform(geometry["forward"], shape(f["geometry"])), f["properties"]["height_m"])
                       for f in context_features]
    roofs = unary_union(geometry["footprints"] + [p for p, _ in context_objects])
    outdoor = site.difference(roofs)
    center = geometry["site"].centroid
    results, features = [], []
    for hour in range(8, 18):
        east, north, up = solar_position(conditions.solar_date, hour, center.y, center.x)
        pieces = []
        objects = context_objects + list(zip(geometry["footprints"], geometry["heights"])) + list(zip(
            geometry["trees"], [tree.height_m for tree in design.trees]))
        for polygon, height in objects:
            if up > .01:
                pieces.append(sweep(polygon, -height*east/up, -height*north/up))
        shadow = unary_union(pieces).difference(roofs).intersection(site.buffer(300)) if pieces else Polygon()
        inside = shadow.intersection(outdoor)
        results.append({"hour_local": hour, "sun_elevation_degrees": math.degrees(math.asin(max(-1, min(1, up)))),
                        "outdoor_shaded_m2": inside.area, "neighbour_shadow_m2": shadow.difference(site).area,
                        "outdoor_shaded_percent": inside.area/outdoor.area*100 if outdoor.area else 0})
        if hour in (9, 12, 15) and not shadow.is_empty:
            features.append({"type": "Feature", "geometry": mapping(transform(geometry["backward"], shadow)),
                             "properties": {"hour_local": hour, "kind": "estimated", "feature": "shadow"}})
    return {"engine": "solar-geometry-2", "kind": "estimated", "date": str(conditions.solar_date),
            "hourly": results, "mean_outdoor_shaded_percent": sum(x["outdoor_shaded_percent"] for x in results)/10,
            "map": {"type": "FeatureCollection", "features": features},
            "surrounding_buildings": surroundings or {"type": "FeatureCollection", "features": []},
            "surrounding_building_count": len(context_features),
            "limitations": "Flat ground, opaque tree prisms, fixed mapped surrounding buildings clipped within 300 m; coverage/heights may be incomplete or assumed. Neighbour shadow includes fixed context shadows on outdoor ground. Shade is not air temperature or Tmrt."}
