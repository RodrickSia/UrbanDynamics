"""Import OSM topology; OD and the private site connector remain estimates."""
import heapq
import math
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def write_osm(document, path):
    root = ET.Element("osm", version="0.6", generator="UrbanDynamics")
    nodes = {}
    ways = []
    for item in document.get("elements", []):
        if item["type"] == "node":
            nodes[item["id"]] = item
        elif item["type"] == "way" and item.get("tags", {}).get("highway"):
            geometry = item.get("geometry", [])
            if len(geometry) != len(item.get("nodes", [])):
                raise ValueError("OSM road extract lacks full node geometry")
            ways.append(item)
            for identifier, coord in zip(item["nodes"], geometry):
                nodes.setdefault(identifier, {"id": identifier, **coord})
    if not ways:
        raise ValueError("Snapshot contains no OSM roads")
    if len(nodes) > 20000 or len(ways) > 5000:
        raise ValueError("OSM network exceeds pilot size; fetch a smaller area")
    for identifier, item in sorted(nodes.items()):
        node = ET.SubElement(root, "node", id=str(identifier), lon=str(item["lon"]), lat=str(item["lat"]), version="1")
        for key, value in item.get("tags", {}).items():
            ET.SubElement(node, "tag", k=key, v=str(value))
    for item in sorted(ways, key=lambda x: x["id"]):
        way = ET.SubElement(root, "way", id=str(item["id"]), version="1")
        for identifier in item["nodes"]:
            ET.SubElement(way, "nd", ref=str(identifier))
        for key, value in item["tags"].items():
            ET.SubElement(way, "tag", k=key, v=str(value))
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def route_between(network, start, end, vclass="passenger"):
    path, _ = network.getShortestPath(start, end, vClass=vclass)
    if path is None or any(not edge.allows("motorcycle") for edge in path):
        return None
    return " ".join(edge.getID() for edge in path)


def prepare(directory, binary, document, site_center, design, execute, bbox):
    # eclipse-sumo ships matching Python helpers in SUMO_HOME/tools.
    import sumo
    tool_path = str(Path(sumo.SUMO_HOME)/"tools")
    if tool_path not in sys.path:
        sys.path.append(tool_path)
    import sumolib
    write_osm(document, directory/"source.osm.xml")
    execute([str(binary), "--osm-files", "source.osm.xml", "--output-file", "public.xml",
             "--keep-edges.by-vclass", "passenger,motorcycle", "--keep-edges.in-geo-boundary", ",".join(str(v) for v in bbox),
             "--geometry.remove", "true", "--no-turnarounds", "true"], directory)
    network = sumolib.net.readNet(str(directory/"public.xml"))
    edges = [e for e in network.getEdges() if e.allows("passenger") and e.allows("motorcycle") and e.getLength() >= 20]
    if len(edges) < 4 or len(edges) > 4000:
        raise ValueError("Pilot requires 4–4,000 drivable edges")
    x, y = network.convertLonLat2XY(*site_center)
    # Pick a connected public junction near the site; this is explicitly an
    # assumed access point, not a cadastral/observed entrance.
    candidates = {e.getFromNode().getID(): e.getFromNode() for e in edges}
    eligible = [n for n in candidates.values() if any(e in edges for e in n.getIncoming()) and any(e in edges for e in n.getOutgoing())]
    nearest = min(eligible, key=lambda n: math.dist(n.getCoord(), (x, y))) if eligible else None
    if nearest is None or math.dist(nearest.getCoord(), (x, y)) > 500:
        raise ValueError("No connected OSM access junction within 500 m; choose a pilot nearer a road")
    if math.dist(nearest.getCoord(), (x, y)) < 30:
        y += 40
    nodes = ET.Element("nodes")
    ET.SubElement(nodes, "node", id="project_gate", x=str(x), y=str(y))
    ET.ElementTree(nodes).write(directory/"access.nodes.xml", encoding="utf-8")
    patches = ET.Element("edges")
    for identifier, a, b in (("project_in", nearest.getID(), "project_gate"), ("project_out", "project_gate", nearest.getID())):
        ET.SubElement(patches, "edge", id=identifier, **{"from": a, "to": b, "speed": "8.33", "numLanes": str(design.gate_lanes),
                                                       "allow": "passenger motorcycle", "priority": "1"})
    ET.ElementTree(patches).write(directory/"access.edges.xml", encoding="utf-8")
    connections = ET.Element("connections")
    for edge in nearest.getIncoming():
        if edge.allows("passenger") and edge.allows("motorcycle"):
            ET.SubElement(connections, "connection", **{"from": edge.getID(), "to": "project_in", "fromLane": "0", "toLane": "0"})
    ET.ElementTree(connections).write(directory/"access.connections.xml", encoding="utf-8")
    execute([str(binary), "--sumo-net-file", "public.xml", "--node-files", "access.nodes.xml", "--edge-files", "access.edges.xml",
             "--connection-files", "access.connections.xml",
             "--output-file", "network.xml", "--no-turnarounds", "true"], directory)
    network = sumolib.net.readNet(str(directory/"network.xml"))
    edges = [e for e in network.getEdges() if e.allows("passenger") and e.allows("motorcycle") and not e.getID().startswith("project_")]
    def reachable(edge, reverse=False):
        seen, pending = {edge.getID()}, [edge]
        while pending:
            item = pending.pop()
            for neighbor in (item.getIncoming() if reverse else item.getOutgoing()):
                if neighbor.getID() not in seen and neighbor.allows("passenger") and neighbor.allows("motorcycle"):
                    seen.add(neighbor.getID())
                    pending.append(neighbor)
        return seen
    inbound = reachable(network.getEdge("project_in"), reverse=True)
    outbound = reachable(network.getEdge("project_out"))
    # Choose representative distant approaches in 8 angular sectors. These are
    # a bounded OD prior, not observed boundary flows or fitted camera counts.
    def select_boundary(reached):
        sectors = {}
        for edge in sorted(edges, key=lambda e: e.getID()):
            if edge.getID() not in reached:
                continue
            a, b = edge.getFromNode().getCoord(), edge.getToNode().getCoord()
            coord = ((a[0]+b[0])/2, (a[1]+b[1])/2)
            angle = int((math.atan2(coord[1]-y, coord[0]-x)+math.pi)/(2*math.pi)*8) % 8
            distance = math.dist(coord, (x, y))
            if angle not in sectors or distance > sectors[angle][0]:
                sectors[angle] = (distance, edge)
        return [v[1] for _, v in sorted(sectors.items())]
    origins, destinations = select_boundary(inbound), select_boundary(outbound)
    routes = {"background": [], "in": [], "out": []}
    for start in origins:
        for end in destinations:
            if start == end:
                continue
            path = route_between(network, start, end)
            if path and "project_" not in path:
                routes["background"].append({"edges": path, "weight": 1/max(50, math.dist(start.getFromNode().getCoord(), end.getFromNode().getCoord()))**2})
        path = route_between(network, start, network.getEdge("project_in"))
        if path:
            routes["in"].append({"edges": path, "weight": 1/max(50, math.dist(start.getFromNode().getCoord(), (x, y)))**2})
    for end in destinations:
        path = route_between(network, network.getEdge("project_out"), end)
        if path:
            routes["out"].append({"edges": path, "weight": 1/max(50, math.dist(end.getToNode().getCoord(), (x, y)))**2})
    if any(not values for values in routes.values()):
        raise ValueError("OSM network has no routable boundary/site OD; a wider snapshot may be needed")
    features = []
    public_length = 0
    for edge in network.getEdges():
        if not edge.allows("passenger"):
            continue
        coords = [network.convertXY2LonLat(*p) for p in edge.getShape()]
        connector = edge.getID().startswith("project_")
        public_length += 0 if connector else edge.getLength()
        features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                         "properties": {"id": edge.getID(), "kind": "synthetic_access" if connector else "osm_import",
                                        "lanes": len(edge.getLanes()), "speed_m_s": edge.getSpeed()}})
    return routes, {"type": "FeatureCollection", "features": features}, {
        "kind": "osm_topology_with_estimated_demand", "public_directed_length_m": public_length,
        "nodes": len(network.getNodes()), "directed_edges": len(network.getEdges()), "boundary_approaches": len(origins), "boundary_destinations": len(destinations),
        "access_junction": nearest.getID(), "connector_kind": "synthetic_nearest_junction",
        "od_method": "Boundary approach pairs weighted by inverse squared distance; not fitted local OD",
        "signal_method": "OSM signal tags where present; phase timings generated by netconvert, not surveyed"}


def walking_graph(document, forward):
    """Frozen OSM pedestrian topology; motor-vehicle one-way is not foot one-way."""
    graph, points = {}, {}
    geographic, segments = {}, []
    for item in document.get("elements", []):
        tags = item.get("tags", {})
        explicit_foot = tags.get("foot") in ("yes", "designated", "permissive")
        if item["type"] != "way" or not tags.get("highway") or tags.get("foot") in ("no", "private") or (tags.get("access") in ("private", "no") and not explicit_foot) or tags.get("highway") in ("motorway", "motorway_link", "construction", "proposed"):
            continue
        identifiers, geometry = item.get("nodes", []), item.get("geometry", [])
        if len(identifiers) != len(geometry):
            continue
        for identifier, coord in zip(identifiers, geometry):
            points[identifier] = forward(coord["lon"], coord["lat"])
            geographic[identifier] = (coord["lon"], coord["lat"])
            graph.setdefault(identifier, [])
        for a, b in zip(identifiers, identifiers[1:]):
            length = math.dist(points[a], points[b])
            if tags.get("oneway:foot") != "-1":
                graph[a].append((b, length))
            if tags.get("oneway:foot") not in ("yes", "1", "true"):
                graph[b].append((a, length))
            segments.append([geographic[a], geographic[b]])
    return {"graph": graph, "points": points, "geographic": geographic, "segments": segments}


def walking_route(topology, origin, destination, forward, maximum_connector_m=300):
    """Shortest OSM path plus explicitly estimated endpoint connectors; no fallback."""
    graph, points = topology["graph"], topology["points"]
    if not graph:
        return None
    start, finish = forward(*origin), forward(*destination)
    a = min(graph, key=lambda n: math.dist(points[n], start))
    b = min(graph, key=lambda n: math.dist(points[n], finish))
    connectors = math.dist(points[a], start)+math.dist(points[b], finish)
    if max(math.dist(points[a], start), math.dist(points[b], finish)) > maximum_connector_m:
        return None
    queue, distances = [(0, a)], {a: 0}
    parents = {}
    while queue:
        distance, node = heapq.heappop(queue)
        if distance > distances[node]:
            continue
        if node == b:
            identifiers = [b]
            while identifiers[-1] != a:
                identifiers.append(parents[identifiers[-1]])
            identifiers.reverse()
            coords = [origin]+[topology["geographic"][n] for n in identifiers]+[destination]
            return {"distance_m": distance+connectors, "network_distance_m": distance,
                    "connector_distance_m": connectors, "node_ids": identifiers,
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "method": "osm_shortest_foot_path_with_estimated_connectors"}
        for neighbor, length in graph[node]:
            value = distance+length
            if value < distances.get(neighbor, float("inf")):
                distances[neighbor] = value
                parents[neighbor] = node
                heapq.heappush(queue, (value, neighbor))
    return None


def walking_distance(document, origin, destination, forward):
    route = walking_route(walking_graph(document, forward), origin, destination, forward)
    return route["distance_m"] if route else None
