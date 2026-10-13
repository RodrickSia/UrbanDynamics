"""Capacity-constrained school allocation on an explicit synthetic walking graph.

Successive shortest residual paths maximize served students first, then minimize
total walk distance. Reverse edges allow reassignment: nearest-first greedy
allocation would strand groups with only one reachable school.
"""
import math

from shapely.geometry import Point, LineString, shape, mapping
from shapely.ops import transform

from ..integrated.context import projection


def allocate(groups, facilities, distances, maximum_distance):
    # All collections are canonicalized by identity before resolving equal costs.
    groups = sorted(groups, key=lambda item: item["id"])
    facilities = sorted(facilities, key=lambda item: item["id"])
    n = len(groups)+len(facilities)+2
    source, sink = n-2, n-1
    graph = [[] for _ in range(n)]
    candidates = []

    def edge(start, end, capacity, cost):
        forward = [end, len(graph[end]), capacity, cost, capacity]
        reverse = [start, len(graph[start]), 0, -cost, 0]
        graph[start].append(forward)
        graph[end].append(reverse)
        return forward

    for i, group in enumerate(groups):
        edge(source, i, group["students"], 0)
        for j, facility in enumerate(facilities):
            distance = distances[group["id"], facility["id"]]
            capacity = facility["available_places"]
            if distance <= maximum_distance and capacity is not None:
                arc = edge(i, len(groups)+j, group["students"], distance)
                candidates.append((group, facility, distance, arc))
    for j, facility in enumerate(facilities):
        edge(len(groups)+j, sink, facility["available_places"] or 0, 0)
    while True:
        distance = [math.inf]*n
        parent = [None]*n
        distance[source] = 0
        for _ in range(n-1):
            changed = False
            for start in range(n):
                if not math.isfinite(distance[start]):
                    continue
                for index, arc in enumerate(graph[start]):
                    end, _, capacity, cost, _ = arc
                    if capacity > 0 and distance[start]+cost < distance[end]-1e-9:
                        distance[end] = distance[start]+cost
                        parent[end] = (start, index)
                        changed = True
            if not changed:
                break
        if parent[sink] is None:
            break
        amount, node = math.inf, sink
        while node != source:
            start, index = parent[node]
            amount = min(amount, graph[start][index][2])
            node = start
        node = sink
        while node != source:
            start, index = parent[node]
            arc = graph[start][index]
            arc[2] -= amount
            graph[node][arc[1]][2] += amount
            node = start
    return [{"group_id": group["id"], "facility_id": facility["id"],
             "students": arc[4]-arc[2], "distance_m": distance}
            for group, facility, distance, arc in candidates if arc[4] > arc[2]]


def evaluate(study, parcel_results, background=None):
    forward, backward = projection(shape(study.study_area.model_dump()))
    projects = {p.id: p for p in study.projects}
    background_groups = background["school_groups"] if background is not None else [g.model_dump(mode="json") for g in sorted(study.background_school_groups, key=lambda g: g.id)]
    background_residents = background["residents"] if background is not None else study.background_residents
    groups = [{"id": "background_"+g["id"], "students": g["students"],
               "point": transform(forward, Point(g["location"])), "source": g["source"]}
              for g in background_groups]
    facilities = [{"id": "existing_"+f.id, "available_places": None if f.capacity_places is None else f.capacity_places-f.reserved_places,
                   "point": transform(forward, Point(f.location)), "source": f.source,
                   "capacity_places": f.capacity_places, "reserved_places": f.reserved_places}
                  for f in sorted(study.school_facilities, key=lambda f: f.id)]
    for parcel in parcel_results:
        project = projects[parcel["id"]]
        design = project.development if parcel["active"] else project.baseline
        point = transform(forward, shape(project.site.model_dump())).centroid
        students = math.ceil(sum(b.residents for b in design.buildings)*study.school_age_fraction)
        if students:
            groups.append({"id": "project_"+project.id, "students": students, "point": point,
                           "source": "Resident count times explicit synthetic school-age fraction, rounded up per parcel"})
        schools = [b for b in design.buildings if b.use == "school"]
        if schools:
            capacity = sum(b.service_capacity for b in schools)
            facilities.append({"id": "project_"+project.id, "point": point,
                               "available_places": capacity if capacity > 0 else None, "capacity_places": capacity if capacity > 0 else None, "reserved_places": 0,
                               "source": "Design capacity of school buildings only; healthcare capacity excluded"})
    # The same hypothetical spine is held fixed across states. Every location
    # has a perpendicular pedestrian connector. This is network routing on the
    # declared graph, not a claim about real sidewalks/crossing permissions.
    parcel_points = [transform(forward, shape(p.site.model_dump())).centroid for p in study.projects]
    spine_y = max(p.y for p in parcel_points)+150

    def path(a, b):
        if a.equals(b):
            return LineString([a, b]), 0.0
        points = [(a.x, a.y), (a.x, spine_y), (b.x, spine_y), (b.x, b.y)]
        line = LineString(points)
        return line, line.length

    osm_mode = study.data_mode == "demo_system"
    if osm_mode:
        from .system_demo import load
        from ..integrated.road_network import walking_graph, walking_route
        topology = walking_graph(load(study.system_snapshot_id).get("osm", {}), forward)
    routes, route_metadata = {}, {}
    for group in groups:
        for facility in facilities:
            key = group["id"], facility["id"]
            if osm_mode:
                origin = list(transform(backward, group["point"]).coords[0])
                destination = list(transform(backward, facility["point"]).coords[0])
                route = walking_route(topology, origin, destination, forward)
                if route:
                    routes[key] = (transform(forward, shape(route["geometry"])), route["distance_m"])
                    route_metadata[key] = {k: route[k] for k in ("network_distance_m", "connector_distance_m", "method")}
                else:
                    routes[key] = (None, math.inf)
            else:
                routes[key] = path(group["point"], facility["point"])
    distances = {key: value[1] for key, value in routes.items()}
    assignments = allocate(groups, facilities, distances, study.school_max_walk_m)
    served = sum(a["students"] for a in assignments)
    demand = sum(g["students"] for g in groups)
    unknown = any(f["available_places"] is None for f in facilities)
    missing_background = background_residents > 0 and not background_groups
    uncertain = unknown or missing_background or any(p.baseline_occupancy == "unknown" for p in study.projects)
    assigned_by_group = {g["id"]: sum(a["students"] for a in assignments if a["group_id"] == g["id"]) for g in groups}
    assigned_by_school = {f["id"]: sum(a["students"] for a in assignments if a["facility_id"] == f["id"]) for f in facilities}
    accesses = []
    for group in groups:
        reachable = [f for f in facilities if distances[group["id"], f["id"]] <= study.school_max_walk_m]
        nearest = min((distances[group["id"], f["id"]] for f in facilities if math.isfinite(distances[group["id"], f["id"]])), default=None)
        accesses.append({"id": group["id"], "students": group["students"], "assigned_students": assigned_by_group[group["id"]],
                         "nearest_school_distance_m": nearest, "reachable_facility_ids": sorted(f["id"] for f in reachable),
                         "unroutable_facility_ids": sorted(f["id"] for f in facilities if not math.isfinite(distances[group["id"], f["id"]]))})
    features = [{"type": "Feature", "geometry": mapping(transform(backward, routes[a["group_id"], a["facility_id"]][0])),
                 "properties": {**a, "walk_minutes": a["distance_m"]/study.school_walk_speed_m_s/60,
                                "service_kind": "school", "source_kind": "mixed_sourced_inputs" if osm_mode else "synthetic",
                                "method": "osm_foot_path_capacity_allocation" if osm_mode else "synthetic_spine_capacity_allocation",
                                **route_metadata.get((a["group_id"], a["facility_id"]), {})}}
                for a in assignments]
    # Publish routable access even when enrollment/capacity is unavailable.
    if osm_mode:
        assigned_pairs = {(a["group_id"], a["facility_id"]) for a in assignments}
        for key, (line, distance) in routes.items():
            if line is not None and key not in assigned_pairs:
                features.append({"type": "Feature", "geometry": mapping(transform(backward, line)),
                    "properties": {"group_id": key[0], "facility_id": key[1], "distance_m": distance,
                        "walk_minutes": distance/study.school_walk_speed_m_s/60,
                        "students": None, "allocation_status": "access_only_not_enrollment",
                        "within_walk_threshold": distance <= study.school_max_walk_m,
                        "service_kind": "school", "source_kind": "mixed_sourced_inputs", **route_metadata[key]}})
    facility_features = [{"type": "Feature", "id": f["id"], "geometry": mapping(transform(backward, f["point"])),
                          "properties": {k: v for k, v in f.items() if k != "point"} |
                                        {"allocated_places": assigned_by_school[f["id"]],
                                         "source_kind": "mixed_sourced_inputs" if osm_mode else "synthetic",
                                         "capacity_source_kind": "unknown" if f["capacity_places"] is None else "declared_scenario",
                                         "service_kind": "school"}}
                         for f in facilities]
    return {"service_kind": "school", "source_kind": "mixed_sourced_inputs" if osm_mode else "synthetic", "comparability": "insufficient_data" if uncertain else "scenario_only",
            "walking_method": "osm_shortest_foot_path_with_estimated_connectors" if osm_mode else "synthetic_spine",
            "unroutable_pairs": [{"group_id": k[0], "facility_id": k[1]} for k,v in routes.items() if v[0] is None],
            "metrics": {"school_demand_students": demand, "school_served_students": served,
                        "school_unserved_students": None if uncertain else demand-served,
                        "school_mean_assigned_walk_m": sum(a["students"]*a["distance_m"] for a in assignments)/served if served else None},
            "assignments": assignments, "groups": accesses, "facilities": facility_features,
            "map": {"type": "FeatureCollection", "features": features+facility_features},
            "validity": {"capacity_respected": all(f["available_places"] is None or assigned_by_school[f["id"]] <= f["available_places"] for f in facilities),
                         "demand_respected": all(assigned_by_group[g["id"]] <= g["students"] for g in groups)},
            "unknown_capacity_facility_ids": [f["id"] for f in facilities if f["available_places"] is None],
            "background_demand_missing": missing_background,
            "objective": "Maximize served students within walk threshold, then minimize total assigned walk distance",
            "limitations": ["OSM pedestrian topology with straight endpoint connectors up to 300 m each; no verified sidewalks, crossings, gates or enrollment eligibility. Disconnected paths remain unavailable." if osm_mode else "Synthetic pedestrian spine and connectors; no observed sidewalks, crossings or enrollment eligibility.",
                            "Reserved places exclude modeled groups; school daily_users are operational trips, not a second enrollment demand.",
                            "School places are not healthcare beds or park capacity. Unserved is unknown when capacity/background/occupancy is missing. A school building with default zero design capacity is treated as unknown, not a verified closed school."]}
