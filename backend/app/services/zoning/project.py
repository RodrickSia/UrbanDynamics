"""Project a zoning-plan document into queryable PostGIS rows.

The document stays the editor source of truth. These rows are 2D footprints
and masks only; undo stacks are not copied.
"""
import json
from pathlib import Path

from psycopg.types.json import Jsonb

_SCRIPT = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def catalog_path():
    bundled = Path(__file__).with_name("zoningCatalog.json")
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parents[4] / "frontend/src/features/zoning/zoningCatalog.json"


def load_catalog():
    return json.loads(catalog_path().read_text(encoding="utf-8"))


def execute_script(connection, sql):
    for statement in sql.split(";"):
        if statement.strip():
            connection.execute(statement)


def ensure_schema(connection):
    execute_script(connection, _SCRIPT)
    connection.executemany(
        'INSERT INTO plans.zone_type_catalog (code, name, description, category, "group", land_use_codes) '
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (code) DO UPDATE SET "
        "name = EXCLUDED.name, description = EXCLUDED.description, category = EXCLUDED.category, "
        '"group" = EXCLUDED."group", land_use_codes = EXCLUDED.land_use_codes',
        [(row["code"], row["name"], row["description"], row["category"], row.get("group") or "",
          row.get("land_use_codes") or "") for row in load_catalog()])


def project_rows(document, catalog_codes):
    """Current plan, scenarios, zones, buildings, and masks. Undo history is ignored."""
    plan_id = str(document["id"])
    plan = {
        "id": plan_id, "name": document["name"], "description": document.get("description") or "",
        "horizon": document.get("horizon"), "status": document["status"],
        "jurisdiction": document.get("jurisdiction"), "revision": document["revision"],
        "area_m2": document["area_m2"], "study_area": json.dumps(document["study_area"]),
        "baseline": document["baseline"], "created_at": document["created_at"],
        "updated_at": document["updated_at"],
    }
    types, scenarios, zones, buildings, masks = [], [], [], [], []
    for position, item in enumerate(document.get("types") or []):
        code = item["code"]
        types.append({
            "plan_id": plan_id, "id": item["id"], "code": code, "name": item["name"],
            "color": item["color"], "description": item.get("description") or "",
            "uses": item.get("uses") or "", "max_height": item.get("max_height"),
            "max_floors": item.get("max_floors"), "coverage": item.get("coverage"),
            "far": item.get("far"), "setback_front": item.get("setback_front"),
            "setback_side": item.get("setback_side"), "setback_rear": item.get("setback_rear"),
            "source": item.get("source") or "", "version": item["version"], "status": item["status"],
            "origin_id": item.get("origin_id"), "catalog_code": code if code in catalog_codes else None,
            "position": position,
        })
    for position, scenario in enumerate(document.get("scenarios") or []):
        scenario_id = scenario["id"]
        scenarios.append({
            "plan_id": plan_id, "id": scenario_id, "name": scenario["name"],
            "description": scenario.get("description") or "", "kind": scenario["kind"],
            "locked": scenario["locked"], "copied_from": scenario.get("copied_from"),
            "revision": scenario.get("revision"), "created_at": scenario.get("created_at"),
            "updated_at": scenario.get("updated_at"), "created_by": scenario.get("created_by"),
            "position": position,
        })
        zones.extend(_placed(plan_id, scenario_id, scenario.get("zones") or [], _zone))
        buildings.extend(_placed(plan_id, scenario_id, scenario.get("buildings") or [], _building))
        masks.extend(_placed(plan_id, scenario_id, scenario.get("demolition_masks") or [], _mask))
    parcels = [_parcel(plan_id, item) for item in (document.get("parcels") or {}).values()]
    return {"plan": plan, "types": types, "scenarios": scenarios, "zones": zones,
            "buildings": buildings, "parcels": parcels, "masks": masks}


def project(connection, document):
    codes = {row["code"] for row in load_catalog()}
    rows = project_rows(document, codes)
    plan_id = rows["plan"]["id"]
    connection.execute("DELETE FROM plans.plan WHERE id = %s", (plan_id,))
    plan = rows["plan"]
    connection.execute(
        "INSERT INTO plans.plan (id, name, description, horizon, status, jurisdiction, revision, "
        "area_m2, study_area, baseline, created_at, updated_at) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s)",
        (plan["id"], plan["name"], plan["description"], plan["horizon"], plan["status"],
         plan["jurisdiction"], plan["revision"], plan["area_m2"], plan["study_area"],
         Jsonb(plan["baseline"]), plan["created_at"], plan["updated_at"]))
    _insert_types(connection, rows["types"])
    _insert_scenarios(connection, rows["scenarios"])
    _insert_zones(connection, rows["zones"])
    _insert_buildings(connection, rows["buildings"])
    _insert_parcels(connection, rows["parcels"])
    _insert_masks(connection, rows["masks"])


def backfill(connection):
    pending = connection.execute(
        "SELECT z.document FROM zoning_plans z "
        "WHERE NOT EXISTS (SELECT 1 FROM plans.plan p WHERE p.id = z.id)").fetchall()
    for (document,) in pending:
        project(connection, json.loads(document) if isinstance(document, str) else document)


def _placed(plan_id, scenario_id, items, convert):
    return [convert(plan_id, scenario_id, position, item) for position, item in enumerate(items)]


def _zone(plan_id, scenario_id, position, item):
    label = item.get("label_point")
    return {
        "plan_id": plan_id, "scenario_id": scenario_id, "id": item["id"],
        "type_id": item.get("type_id"), "origin_id": item.get("origin_id"),
        "geom": json.dumps(item["geometry"]),
        "label_x": label[0] if isinstance(label, (list, tuple)) and len(label) >= 2 else None,
        "label_y": label[1] if isinstance(label, (list, tuple)) and len(label) >= 2 else None,
        "area_m2": item.get("area_m2"), "revision": item.get("revision"),
        "source": item.get("source"), "position": position,
    }


def _building(plan_id, scenario_id, position, item):
    return {
        "plan_id": plan_id, "scenario_id": scenario_id, "id": item["id"],
        "parcel_id": item.get("parcel_id"), "origin_id": item.get("origin_id"),
        "name": item.get("name"), "geom": json.dumps(item["geometry"]),
        "floors": item.get("floors"), "floor_height": item.get("floor_height"),
        "height_m": item.get("height_m"), "footprint_m2": item.get("footprint_m2"),
        "space_use_id": item.get("space_use_id"), "counts_gfa": item.get("counts_gfa"),
        "counts_far": item.get("counts_far"), "color": item.get("color"),
        "status": item.get("status"), "origin": item.get("origin"),
        "template_id": item.get("template_id"), "template_version": item.get("template_version"),
        "ground_anchor": item.get("ground_anchor"), "floor_stack": item.get("floor_stack"),
        "floor_overrides": item.get("floor_overrides"), "position": position,
    }


def _mask(plan_id, scenario_id, position, item):
    return {
        "plan_id": plan_id, "scenario_id": scenario_id, "id": item["id"],
        "parcel_id": item.get("parcel_id"), "geom": json.dumps(item["geometry"]),
        "status": item.get("status"), "position": position,
    }


def _parcel(plan_id, item):
    return {
        "plan_id": plan_id, "parcel_id": str(item["id"]), "geom": json.dumps(item["geometry"]),
        "area_m2": item.get("area_m2"), "land_use": item.get("land_use"),
        "source": item.get("source"), "status": item.get("status"),
        "captured_at": item.get("captured_at"),
    }


def _insert_types(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.zone_type (plan_id, id, code, name, color, description, uses, max_height, "
        "max_floors, coverage, far, setback_front, setback_side, setback_rear, source, version, status, "
        "origin_id, catalog_code, position) VALUES "
        "(%(plan_id)s, %(id)s, %(code)s, %(name)s, %(color)s, %(description)s, %(uses)s, %(max_height)s, "
        "%(max_floors)s, %(coverage)s, %(far)s, %(setback_front)s, %(setback_side)s, %(setback_rear)s, "
        "%(source)s, %(version)s, %(status)s, %(origin_id)s, %(catalog_code)s, %(position)s)", rows)


def _insert_scenarios(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.scenario (plan_id, id, name, description, kind, locked, copied_from, revision, "
        "created_at, updated_at, created_by, position) VALUES "
        "(%(plan_id)s, %(id)s, %(name)s, %(description)s, %(kind)s, %(locked)s, %(copied_from)s, "
        "%(revision)s, %(created_at)s, %(updated_at)s, %(created_by)s, %(position)s)", rows)


def _insert_zones(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.zone (plan_id, scenario_id, id, type_id, origin_id, geom, label_point, "
        "area_m2, revision, source, position) VALUES "
        "(%(plan_id)s, %(scenario_id)s, %(id)s, %(type_id)s, %(origin_id)s, "
        "ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), "
        "CASE WHEN %(label_x)s IS NULL THEN NULL "
        "ELSE ST_SetSRID(ST_MakePoint(%(label_x)s, %(label_y)s), 4326) END, "
        "%(area_m2)s, %(revision)s, %(source)s, %(position)s)", rows)


def _insert_buildings(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.building (plan_id, scenario_id, id, parcel_id, origin_id, name, geom, floors, "
        "floor_height, height_m, footprint_m2, space_use_id, counts_gfa, counts_far, color, status, "
        "origin, template_id, template_version, ground_anchor, floor_stack, floor_overrides, position) "
        "VALUES (%(plan_id)s, %(scenario_id)s, %(id)s, %(parcel_id)s, %(origin_id)s, %(name)s, "
        "ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(floors)s, %(floor_height)s, %(height_m)s, "
        "%(footprint_m2)s, %(space_use_id)s, %(counts_gfa)s, %(counts_far)s, %(color)s, %(status)s, "
        "%(origin)s, %(template_id)s, %(template_version)s, %(ground_anchor)s, %(floor_stack)s, "
        "%(floor_overrides)s, %(position)s)",
        [{**row, "ground_anchor": _json(row["ground_anchor"]), "floor_stack": _json(row["floor_stack"]),
          "floor_overrides": _json(row["floor_overrides"])} for row in rows])


def _insert_parcels(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.parcel_snapshot (plan_id, parcel_id, geom, area_m2, land_use, source, status, "
        "captured_at) VALUES (%(plan_id)s, %(parcel_id)s, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), "
        "%(area_m2)s, %(land_use)s, %(source)s, %(status)s, %(captured_at)s)", rows)


def _insert_masks(connection, rows):
    if not rows:
        return
    connection.executemany(
        "INSERT INTO plans.demolition_mask (plan_id, scenario_id, id, parcel_id, geom, status) VALUES "
        "(%(plan_id)s, %(scenario_id)s, %(id)s, %(parcel_id)s, "
        "ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326), %(status)s)", rows)


def _json(value):
    return None if value is None else Jsonb(value)
