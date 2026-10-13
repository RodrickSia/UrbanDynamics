"""Pure common corridor specification used by provenance and netconvert alike."""
import hashlib
import math

from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform

from ..integrated.context import projection
from .parcels import registry


def specification(study):
    if study.traffic_network_mode == "osm_snapshot":
        from .osm_network import source_specification
        return source_specification(study)
    forward, backward = projection(shape(study.study_area.model_dump()))
    projects = sorted(study.projects, key=lambda p: p.id)
    centers = {p.id: transform(forward, shape(p.site.model_dump())).centroid for p in projects}
    physical_ids = registry(study)
    physical_projects = [p for p in projects if physical_ids[p.id] == p.id]
    geometries = {p.id: shape(p.site.model_dump()).normalize().wkb_hex for p in projects}
    solver_ids = {p.id: "p_"+hashlib.sha256(geometries[p.id].encode()).hexdigest()[:24] for p in projects}
    physical_projects.sort(key=lambda p: solver_ids[p.id])
    public_sites = sorted((p.id for p in physical_projects),
                          key=lambda key: (centers[key].x, centers[key].y, geometries[key]))
    y = max(p.y for p in centers.values())+150
    coordinates = {"west": (min(p.x for p in centers.values())-350, y),
                   "east": (max(p.x for p in centers.values())+350, y)}
    for index, identifier in enumerate(public_sites):
        x = max(centers[identifier].x, coordinates.get(f"j{index-1}", (-math.inf, 0))[0]+80)
        coordinates[f"j{index}"] = (x, y)
    coordinates["east"] = (max(coordinates["east"][0], coordinates[f"j{len(public_sites)-1}"][0]+350), y)
    junction_for = {p.id: f"j{public_sites.index(p.id)}" for p in physical_projects}
    for p in physical_projects:
        coordinates[f"gate_{solver_ids[p.id]}"] = (centers[p.id].x, centers[p.id].y)
    nodes = [{"id": name, "x": x, "y": yy,
              "type": "traffic_light" if name.startswith("j") else "priority"}
             for name, (x, yy) in coordinates.items()]
    public_nodes = ["west"]+[f"j{i}" for i in range(len(public_sites))]+["east"]
    edges, features, corridor = [], [], {}

    def edge(a, b, identifier, private=False, lanes=1):
        edges.append({"id": identifier, "from": a, "to": b, "numLanes": lanes,
                      "speed": "8.33" if private else "13.89", "allow": "passenger motorcycle",
                      "priority": "1" if private else "2"})
        features.append({"type": "Feature", "id": identifier,
                         "geometry": mapping(transform(backward, LineString([coordinates[a], coordinates[b]]))),
                         "properties": {"edge_id": identifier, "source_kind": "synthetic", "private": private}})
    for a, b in zip(public_nodes, public_nodes[1:]):
        for start, end in ((a, b), (b, a)):
            identifier = f"road_{start}_{end}"
            corridor[start, end] = identifier
            edge(start, end, identifier)
    for p in physical_projects:
        junction, gate = junction_for[p.id], f"gate_{solver_ids[p.id]}"
        edge(junction, gate, f"{solver_ids[p.id]}_in", True, p.development.gate_lanes)
        edge(gate, junction, f"{solver_ids[p.id]}_out", True, p.development.gate_lanes)
        for feature in features[-2:]:
            feature["properties"]["project_ids"] = sorted(key for key in solver_ids if solver_ids[key] == solver_ids[p.id])
    routes = {"background_west": [corridor[a, b] for a, b in zip(public_nodes, public_nodes[1:])],
              "background_east": [corridor[b, a] for a, b in reversed(list(zip(public_nodes, public_nodes[1:])))]}
    for p in projects:
        physical = physical_ids[p.id]
        solver_id = solver_ids[p.id]
        index = public_nodes.index(junction_for[physical])
        west = [corridor[a, b] for a, b in zip(public_nodes[:index], public_nodes[1:index+1])]
        east = [corridor[b, a] for a, b in reversed(list(zip(public_nodes[index:-1], public_nodes[index+1:])))]
        routes[f"{solver_id}_in_west"] = west+[f"{solver_id}_in"]
        routes[f"{solver_id}_in_east"] = east+[f"{solver_id}_in"]
        routes[f"{solver_id}_out_west"] = [f"{solver_id}_out"]+[corridor[b, a] for a, b in reversed(list(zip(public_nodes[:index], public_nodes[1:index+1])))]
        routes[f"{solver_id}_out_east"] = [f"{solver_id}_out"]+[corridor[a, b] for a, b in zip(public_nodes[index:-1], public_nodes[index+1:])]
    return {"nodes": nodes, "edges": edges, "routes": routes,
            "map": {"type": "FeatureCollection", "features": features},
            "project_to_physical_parcel": physical_ids,
            "project_to_solver_parcel": solver_ids,
            "project_random_keys": {p.id: hashlib.sha256(geometries[p.id].encode()).hexdigest() for p in projects},
            "provenance": {"kind": "synthetic_corridor", "private_accesses": len(physical_projects),
                           "project_to_physical_parcel": physical_ids, "background_can_use_private_access": False,
                           "signal_method": "netconvert-generated timings, not measured",
                           "baseline_basis": "All hypothetical access roads are present in every state; inactive accesses have no project trips."}}
