"""Load SUMO edges, junctions, and connections into PostGIS."""

import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable

from pyproj import CRS, Transformer
from psycopg import sql

from src.pipelines.osm_sumo_hcmc.config import OsmSumoConfig, config
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)
BATCH_SIZE = 5_000


def _shape(
    value: str, transformer: Transformer, offset_x: float, offset_y: float
) -> list[tuple[float, float]]:
    points = []
    for token in value.split():
        x, y = (float(part) for part in token.split(",")[:2])
        lon, lat = transformer.transform(x - offset_x, y - offset_y)
        points.append((lon, lat))
    return points


def run(settings: OsmSumoConfig = config) -> dict[str, int]:
    network = settings.data_dir / "hcmc.net.xml"
    if not network.exists():
        raise FileNotFoundError(f"Missing {network}; run the transform stage first")
    schema = sql.Identifier(settings.database_schema)
    edge_table = sql.SQL("{}.{}").format(schema, sql.Identifier(settings.edge_table))
    junction_table = sql.SQL("{}.{}").format(schema, sql.Identifier(settings.junction_table))
    connection_table = sql.SQL("{}.{}").format(schema, sql.Identifier(settings.connection_table))
    edge_insert = sql.SQL("""INSERT INTO {} (edge_id, from_node, to_node, name, road_type, priority, lane_count, lanes, geom)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))""").format(edge_table)
    junction_insert = sql.SQL("""INSERT INTO {} (junction_id, junction_type, incoming_lanes, internal_lanes, geom)
        VALUES (%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326))""").format(junction_table)
    connection_insert = sql.SQL("""INSERT INTO {} (from_edge, to_edge, from_lane, to_lane, via_lane, direction, state, traffic_light, link_index)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""").format(connection_table)

    counts = {"edges": 0, "junctions": 0, "connections": 0}
    db = connect_to_warehouse()
    try:
        with db.transaction():
            with db.cursor() as cursor:
                cursor.execute(sql.SQL("TRUNCATE {}, {}").format(connection_table, junction_table))
                # TomTom observations reference SUMO edges with ON DELETE SET NULL.
                # DELETE preserves those observations and clears their stale edge
                # matches; TRUNCATE would fail while the referencing rows exist.
                cursor.execute(sql.SQL("DELETE FROM {}").format(edge_table))
                edge_rows, junction_rows, connection_rows = [], [], []
                transformer = offset_x = offset_y = None

                def flush(rows: list, statement, kind: str, prepare: Callable | None = None) -> None:
                    if not rows:
                        return
                    values = prepare(rows) if prepare else rows
                    cursor.executemany(statement, values)
                    counts[kind] += len(rows)
                    rows.clear()

                for event, element in ET.iterparse(network, events=("start", "end")):
                    if event == "start" and element.tag == "location":
                        proj = element.get("projParameter")
                        if not proj:
                            raise ValueError("SUMO network has no projection metadata")
                        source_crs = CRS.from_user_input(proj)
                        transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
                        offset_x, offset_y = (float(value) for value in element.get("netOffset", "0,0").split(","))
                        element.clear()
                        continue
                    if event != "end":
                        continue

                    if element.tag == "edge":
                        edge_id = element.get("id")
                        if edge_id and not edge_id.startswith(":"):
                            lanes = [
                                {
                                    "id": lane.get("id"), "index": int(lane.get("index", 0)),
                                    "speed_mps": float(lane.get("speed", 0)),
                                    "width_m": float(lane.get("width", 0)) if lane.get("width") else None,
                                    "allow": lane.get("allow"), "disallow": lane.get("disallow"),
                                }
                                for lane in element.findall("lane")
                            ]
                            lane = element.find("lane")
                            shape_value = element.get("shape") or (lane.get("shape") if lane is not None else None)
                            points = _shape(shape_value, transformer, offset_x, offset_y) if shape_value else []
                            if len(points) >= 2:
                                edgeshape = {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in points]}
                                edge_rows.append((
                                    edge_id, element.get("from"), element.get("to"), element.get("name"),
                                    element.get("type"), int(element.get("priority", 0)), len(lanes),
                                    json.dumps(lanes), json.dumps(edgeshape),
                                ))
                                if len(edge_rows) >= BATCH_SIZE:
                                    flush(edge_rows, edge_insert, "edges")
                    elif element.tag == "junction":
                        node_id = element.get("id")
                        if node_id and element.get("x") is not None and element.get("y") is not None:
                            lon, lat = transformer.transform(
                                float(element.get("x")) - offset_x,
                                float(element.get("y")) - offset_y,
                            )
                            junction_rows.append((
                                node_id, element.get("type"), element.get("incLanes", "").split(),
                                element.get("intLanes", "").split(), lon, lat,
                            ))
                            if len(junction_rows) >= BATCH_SIZE:
                                flush(junction_rows, junction_insert, "junctions")
                    elif element.tag == "connection":
                        connection_rows.append((
                            element.get("from"), element.get("to"),
                            int(element.get("fromLane", 0)), int(element.get("toLane", 0)),
                            element.get("via"), element.get("dir"), element.get("state"),
                            element.get("tl"), int(element.get("linkIndex")) if element.get("linkIndex") else None,
                        ))
                        if len(connection_rows) >= BATCH_SIZE:
                            flush(connection_rows, connection_insert, "connections")

                    if element.tag in {"edge", "junction", "connection"}:
                        element.clear()

                if transformer is None:
                    raise ValueError("SUMO network has no location projection metadata")
                flush(edge_rows, edge_insert, "edges")
                flush(junction_rows, junction_insert, "junctions")
                flush(connection_rows, connection_insert, "connections")
                cursor.execute(sql.SQL("ANALYZE {} ").format(edge_table))
                cursor.execute(sql.SQL("ANALYZE {} ").format(junction_table))
        logger.info("Loaded SUMO network into PostGIS: %s", counts)
        return counts
    finally:
        db.close()
