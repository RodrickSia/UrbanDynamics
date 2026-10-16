import json
import os
from copy import deepcopy

import psycopg
import pytest

from app.services.zoning.project import _SCRIPT, execute_script, project_rows

POLY = {"type": "Polygon", "coordinates": [
    [[106.76, 10.82], [106.761, 10.82], [106.761, 10.821], [106.76, 10.821], [106.76, 10.82]]]}


def document():
    return {
        "id": "plan-1", "name": "Thu Duc", "description": "", "horizon": None,
        "study_area": deepcopy(POLY), "area_m2": 100.0, "revision": 1,
        "created_at": "2026-10-14T00:00:00+00:00", "updated_at": "2026-10-14T00:00:00+00:00",
        "status": "draft", "jurisdiction": "HCMC pilot",
        "baseline": {"version": "base-1", "status": "unverified"},
        "types": [{"id": "type-1", "code": "RES", "name": "Residential", "color": "#55a99a",
                   "description": "", "uses": "", "version": 1, "status": "proposal"},
                  {"id": "type-2", "code": "CUSTOM", "name": "Custom", "color": "#112233",
                   "version": 1, "status": "proposal"}],
        "scenarios": [
            {"id": "existing", "name": "Existing", "kind": "reference", "locked": True, "zones": [],
             "description": "", "created_at": "2026-10-14T00:00:00+00:00", "revision": 1},
            {"id": "scenario-a", "name": "Scenario A", "kind": "proposal", "locked": False, "zones": [
                {"id": "zone-1", "type_id": "type-1", "geometry": deepcopy(POLY),
                 "label_point": [106.7605, 10.8205], "area_m2": 100.0, "revision": 1,
                 "source": "Scenario proposal"}],
             "buildings": [{"id": "building-1", "parcel_id": "parcel-1", "name": "House",
                            "geometry": deepcopy(POLY), "floors": 2, "floor_height": 3.2,
                            "height_m": 6.4, "footprint_m2": 80.0, "space_use_id": "residential",
                            "counts_gfa": True, "counts_far": True}],
             "demolition_masks": [{"id": "mask-1", "parcel_id": "parcel-1", "geometry": deepcopy(POLY),
                                   "status": "user_proposed"}],
             "_past": [[{"id": "ghost-zone", "geometry": deepcopy(POLY)}]],
             "_dev_past": [{"buildings": [{"id": "ghost-building", "geometry": deepcopy(POLY)}]}],
             "description": "", "revision": 1},
        ],
        "parcels": {"parcel-1": {"id": "parcel-1", "geometry": deepcopy(POLY), "area_m2": 120.0,
                                 "land_use": "ODT", "source": "parcels.plot",
                                 "status": "source_unverified",
                                 "captured_at": "2026-10-14T00:00:00+00:00"}},
    }


def test_projection_is_one_to_many_and_skips_undo_history():
    rows = project_rows(document(), {"RES"})
    assert [item["id"] for item in rows["scenarios"]] == ["existing", "scenario-a"]
    assert [item["id"] for item in rows["buildings"]] == ["building-1"]
    assert [item["id"] for item in rows["zones"]] == ["zone-1"]
    assert [item["id"] for item in rows["masks"]] == ["mask-1"]
    assert rows["buildings"][0]["scenario_id"] == "scenario-a"
    assert rows["zones"][0]["scenario_id"] == "scenario-a"
    assert [item["parcel_id"] for item in rows["parcels"]] == ["parcel-1"]
    assert [item["catalog_code"] for item in rows["types"]] == ["RES", None]
    assert "ghost-building" not in json.dumps(rows)
    assert "ghost-zone" not in json.dumps(rows)


def test_schema_script_ignores_semicolons_in_comments():
    class Connection:
        statements = []

        def execute(self, statement):
            self.statements.append(statement.strip())

    connection = Connection()
    execute_script(connection, _SCRIPT)
    assert connection.statements[0] == "CREATE EXTENSION IF NOT EXISTS postgis"
    assert connection.statements[1] == "CREATE SCHEMA IF NOT EXISTS plans"
    assert len(connection.statements) == 15
    assert all(not statement.startswith("no mesh") for statement in connection.statements)


def test_postgis_schema_bootstraps_once_after_a_committed_transaction(monkeypatch):
    from app.services.zoning import store

    connections = []
    calls = []

    class Connection:
        def __init__(self):
            self.statements = []
            connections.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement):
            self.statements.append(statement)

        def close(self):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://projection-test")
    monkeypatch.delenv("ZONING_STORAGE", raising=False)
    monkeypatch.setattr(store, "_initialized_databases", set())
    monkeypatch.setattr(store, "connect_to_warehouse", Connection)
    monkeypatch.setattr(store, "ensure_schema", lambda _: calls.append("schema"))
    monkeypatch.setattr(store, "backfill", lambda _: calls.append("backfill"))
    with pytest.raises(ValueError):
        with store.database():
            raise ValueError("rollback")
    assert store._initialized_databases == set()
    with store.database():
        pass
    with store.database():
        pass
    assert calls == ["schema", "backfill"] * 2
    assert len(connections[2].statements) == 0


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires real PostGIS")
def test_postgis_tracks_scenarios_and_drops_removed_buildings(monkeypatch):
    url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    from app.services.zoning import store

    saved = document()
    saved["id"] = "plan-projection-test"
    revision = saved["revision"]
    try:
        store.save_new(saved)
        with psycopg.connect(url) as connection:
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM plans.scenario WHERE plan_id = %s), "
                "(SELECT count(*) FROM plans.building WHERE plan_id = %s), "
                "(SELECT count(*) FROM plans.zone WHERE plan_id = %s), "
                "(SELECT count(*) FROM plans.demolition_mask WHERE plan_id = %s), "
                "(SELECT count(*) FROM plans.parcel_snapshot WHERE plan_id = %s), "
                "(SELECT ST_SRID(geom) FROM plans.building WHERE plan_id = %s), "
                "(SELECT ST_SRID(study_area) FROM plans.plan WHERE id = %s), "
                "(SELECT catalog_code FROM plans.zone_type WHERE plan_id = %s AND id = 'type-1')",
                (saved["id"],) * 8).fetchone()
        assert counts == (2, 1, 1, 1, 1, 4326, 4326, "RES")

        def remove_building(current):
            current["scenarios"][1]["buildings"] = []
            current["revision"] += 1
            return current

        updated = store.update(saved["id"], revision, remove_building)
        revision = updated["revision"]
        with psycopg.connect(url) as connection:
            remaining = connection.execute(
                "SELECT count(*) FROM plans.building WHERE plan_id = %s", (saved["id"],)).fetchone()
        assert remaining == (0,)
        assert store.delete(saved["id"], revision) is True
        revision = None
        with psycopg.connect(url) as connection:
            gone = connection.execute(
                "SELECT count(*) FROM plans.plan WHERE id = %s", (saved["id"],)).fetchone()
        assert gone == (0,)
    finally:
        if revision is not None:
            with psycopg.connect(url) as connection:
                connection.execute("DELETE FROM zoning_plans WHERE id = %s", (saved["id"],))
