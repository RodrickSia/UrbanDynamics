from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import zoning as zoning_router
from app.services.zoning import engine, store
from app.services.zoning.geometry import projected
from app.services.zoning.models import Command


def rectangle(west=106.76, south=10.82, east=106.762, north=10.822):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south],
            [east, north], [west, north], [west, south]]]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ZONING_DATA_DIR", str(tmp_path))
    return TestClient(app)


@pytest.fixture
def plan(client):
    response = client.post("/api/v1/zoning/plans", json={"name": "Thu Duc proposal", "study_area": rectangle()})
    assert response.status_code == 201
    return response.json()


def command(client, plan, action, payload=None, scenario_id=None, status=200):
    response = client.post(f"/api/v1/zoning/plans/{plan['id']}/commands", json={
        "revision": plan["revision"], "action": action, "payload": payload or {},
        "scenario_id": scenario_id or plan["scenarios"][1]["id"]})
    assert response.status_code == status, response.text
    return response.json()


def add_type(client, plan, code="MU"):
    return command(client, plan, "add_type", {"type": {"code": code, "name": "Mixed use proposal",
                   "color": "#309284", "coverage": 60, "far": 4}})


def test_current_parcel_land_use_is_separate_from_proposal_zones(client, plan, monkeypatch):
    from app.services import parcels

    monkeypatch.setattr(zoning_router, "warehouse_configured", lambda: True)
    captured = []
    def observed(study_area):
        captured.append(study_area)
        return {"basis": "observed_parcels", "rows": [{
            "code": "OTC", "parcels": 2, "area_m2": 120.0,
            "category": "Residential", "color": "#D79B8C",
        }]}
    monkeypatch.setattr(parcels, "study_land_use", observed)
    response = client.get(f"/api/v1/zoning/plans/{plan['id']}/land-use")
    assert response.status_code == 200
    assert captured == [plan["study_area"]]
    assert response.json()["rows"][0]["code"] == "OTC"
    assert plan["scenarios"][0]["zones"] == []


def test_zoned_parcel_tiles_only_use_saved_proposal_zones(client, plan, monkeypatch):
    from app.services import parcels

    plan = draw(client, add_type(client, plan))
    monkeypatch.setattr(zoning_router, "warehouse_configured", lambda: True)
    captured = []
    def tile(zones, z, x, y):
        captured.append((zones, z, x, y))
        return b"tile"
    monkeypatch.setattr(parcels, "zoned_parcel_vector_tile", tile)
    path = f"/api/v1/zoning/plans/{plan['id']}/zoned-parcels/tiles/12/3262/1928.pbf"
    query = {"revision": plan["revision"], "scenario_id": plan["scenarios"][1]["id"]}
    response = client.get(path, params=query)
    assert response.status_code == 200
    assert response.content == b"tile"
    assert captured[0][0][0]["id"] == plan["scenarios"][1]["zones"][0]["id"]
    assert captured[0][0][0]["geometry"] == plan["scenarios"][1]["zones"][0]["geometry"]
    assert captured[0][1:] == (12, 3262, 1928)
    assert client.get(path, params={**query, "scenario_id": plan["scenarios"][0]["id"]}).status_code == 204
    assert client.get(path, params={**query, "revision": 1}).status_code == 409


def draw(client, plan, geometry=None, policy="preserve"):
    return command(client, plan, "draw", {"geometry": geometry or rectangle(east=106.761),
                   "type_id": plan["types"][0]["id"], "policy": policy})


def test_persistence_reference_and_independent_scenarios(client, plan):
    baseline = deepcopy(plan["scenarios"][0])
    plan = draw(client, add_type(client, plan))
    plan = command(client, plan, "add_scenario", {"name": "Phase 1"})
    clone = plan["scenarios"][-1]
    plan = command(client, plan, "delete_zone", {"zone_id": clone["zones"][0]["id"], "confirm": True}, clone["id"])
    loaded = client.get(f"/api/v1/zoning/plans/{plan['id']}").json()
    assert loaded == plan
    assert loaded["scenarios"][0] == baseline
    assert len(loaded["scenarios"][1]["zones"]) == 1
    assert loaded["scenarios"][2]["zones"] == []
    command(client, plan, "draw", {"geometry": rectangle(), "type_id": plan["types"][0]["id"],
            "policy": "replace"}, plan["scenarios"][0]["id"], status=422)
    command(client, plan, "lock_scenario", {"locked": False}, plan["scenarios"][0]["id"], status=422)


@pytest.mark.parametrize("policy", ["preserve", "replace"])
def test_overlap_preview_matches_saved_topology(client, plan, policy):
    plan = draw(client, add_type(client, plan))
    payload = {"geometry": rectangle(west=106.7605, east=106.7625), "type_id": plan["types"][0]["id"], "policy": policy}
    preview = client.post(f"/api/v1/zoning/plans/{plan['id']}/preview", json={"action": "draw",
        "revision": plan["revision"], "scenario_id": plan["scenarios"][1]["id"], "payload": payload}).json()
    assert preview["overlap_m2"] > 0
    assert preview["clipped_outside_m2"] > 0
    updated = command(client, plan, "draw", payload)
    zones = updated["scenarios"][1]["zones"]
    assert projected(zones[0]["geometry"]).intersection(projected(zones[1]["geometry"])).area < .01
    assert sum(z["area_m2"] for z in zones) == pytest.approx(sum(z["area_m2"] for z in preview["zones"]))
    assert sum(z["area_m2"] for z in zones) == pytest.approx(plan["area_m2"], abs=.1)


def test_split_merge_undo_and_locked_history(client, plan):
    plan = draw(client, add_type(client, plan))
    zone = plan["scenarios"][1]["zones"][0]
    plan = command(client, plan, "split", {"zone_id": zone["id"], "geometry": {
        "type": "LineString", "coordinates": [[106.759, 10.821], [106.763, 10.821]]}})
    zones = plan["scenarios"][1]["zones"]
    assert len(zones) == 2
    assert sum(z["area_m2"] for z in zones) == pytest.approx(zone["area_m2"])
    plan = command(client, plan, "merge", {"zone_ids": [z["id"] for z in zones]})
    assert len(plan["scenarios"][1]["zones"]) == 1
    plan = command(client, plan, "undo")
    assert len(plan["scenarios"][1]["zones"]) == 2
    plan = command(client, plan, "redo")
    assert len(plan["scenarios"][1]["zones"]) == 1
    plan = command(client, plan, "lock_scenario", {"locked": True})
    command(client, plan, "undo", status=422)


def test_revision_conflicts_and_invalid_inputs_preserve_saved_plan(client, plan):
    updated = add_type(client, plan)
    command(client, plan, "rename_plan", {"name": "stale"}, status=409)
    bad = rectangle()
    bad["coordinates"][0][1], bad["coordinates"][0][2] = bad["coordinates"][0][2], bad["coordinates"][0][1]
    command(client, updated, "draw", {"geometry": bad, "type_id": updated["types"][0]["id"], "policy": "replace"}, status=422)
    command(client, updated, "add_type", {"type": {"code": "bad", "name": "Bad", "color": "red", "far": -1}}, status=422)
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == updated


def test_delete_plan_requires_current_revision_and_removes_only_target(client, plan):
    other = client.post('/api/v1/zoning/plans', json={"name": "Keep", "study_area": rectangle()}).json()
    path = f"/api/v1/zoning/plans/{plan['id']}"
    assert client.delete(path, params={"revision": plan["revision"] + 1}).status_code == 409
    assert client.get(path).status_code == 200
    assert client.delete(path, params={"revision": plan["revision"]}).status_code == 204
    assert client.get(path).status_code == 404
    assert client.delete(path, params={"revision": plan["revision"]}).status_code == 404
    assert client.get(f"/api/v1/zoning/plans/{other['id']}").status_code == 200


def test_plan_parcel_tiles_use_saved_study_area_and_revision(client, plan, monkeypatch):
    from app.routers import zoning
    calls = []
    monkeypatch.setattr(zoning, "warehouse_configured", lambda: True)
    monkeypatch.setattr(zoning.parcels, "plan_vector_tile", lambda area, z, x, y:
                        calls.append((area, z, x, y)) or b"tile")
    path = f"/api/v1/zoning/plans/{plan['id']}/parcels/tiles/12/3262/1928.pbf"
    response = client.get(path, params={"revision": plan["revision"]})
    assert response.status_code == 200 and response.content == b"tile"
    assert calls == [(plan["study_area"], 12, 3262, 1928)]
    assert client.get(path, params={"revision": 2}).status_code == 409
    assert client.get(path.replace('/12/3262/1928', '/12/4096/1928'), params={"revision": 1}).status_code == 404


def test_indicators_unknown_controls_and_independent_bounds(client, plan):
    plan = draw(client, add_type(client, plan))
    url = f"/api/v1/zoning/plans/{plan['id']}/indicators?scenario_id={plan['scenarios'][1]['id']}"
    result = client.get(url).json()
    assert result["assigned_m2"] + result["unassigned_m2"] == pytest.approx(plan["area_m2"])
    assert result["changed_m2"] == pytest.approx(result["assigned_m2"])
    assert result["rows"][0]["far_bound_m2"] == pytest.approx(result["assigned_m2"] * 4)
    assert result["rows"][0]["footprint_bound_m2"] == pytest.approx(result["assigned_m2"] * .6)
    assert plan["types"][0]["max_height"] is None
    assert any(f["certainty"] == "unknown" for f in result["findings"])
    same = client.get(url + f"&compare_id={plan['scenarios'][1]['id']}").json()
    assert same["changed_m2"] == pytest.approx(0)


def test_concurrent_updates_do_not_lose_edits(client, plan):
    def update(name):
        try:
            return store.update(plan["id"], 1, lambda p: engine.apply(p, Command(
                revision=1, action="rename_plan", payload={"name": name})))
        except store.Conflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["A", "B"]))
    assert sum(r is not None for r in results) == 1
    assert store.load(plan["id"])["revision"] == 2


def test_shared_types_confirmation_and_lock_protection(client, plan):
    plan = draw(client, add_type(client, plan))
    plan = command(client, plan, "add_scenario", {"name": "B"})
    kind = plan["types"][0]
    from app.services.zoning.models import ZoneType
    fields = {k: v for k, v in kind.items() if k in ZoneType.model_fields}
    fields["far"] = 5
    payload = {"id": kind["id"], "type": fields}
    command(client, plan, "edit_type", payload, status=422)
    plan = command(client, plan, "edit_type", {**payload, "confirm_shared": True})
    assert plan["types"][0]["version"] == 2
    plan = command(client, plan, "lock_scenario", {"locked": True}, plan["scenarios"][-1]["id"])
    command(client, plan, "edit_type", {**payload, "confirm_shared": True}, status=422)
    command(client, plan, "delete_type", {"id": kind["id"]}, status=422)


def test_study_area_clips_proposals_without_changing_reference(client, plan):
    plan = draw(client, add_type(client, plan), rectangle())
    baseline = deepcopy(plan["scenarios"][0])
    reference = deepcopy(plan["baseline"])
    command(client, plan, "study_area", {"geometry": rectangle(east=106.761)}, status=422)
    plan = command(client, plan, "study_area", {"geometry": rectangle(east=106.761), "confirm": True})
    assert plan["scenarios"][0] == baseline
    assert plan["baseline"] == reference
    assert plan["scenarios"][1]["zones"][0]["area_m2"] == pytest.approx(plan["area_m2"], abs=.1)
    assert plan["scenarios"][1]["can_undo"] is False


def test_reshape_preserves_holes_and_rejects_open_rings(client, plan):
    kind_plan = add_type(client, plan)
    polygon = rectangle()
    polygon["coordinates"].append(rectangle(106.7605, 10.8205, 106.761, 10.821)["coordinates"][0])
    plan = draw(client, kind_plan, polygon)
    zone = plan["scenarios"][1]["zones"][0]
    assert len(zone["geometry"]["coordinates"]) == 2
    geometry = deepcopy(zone["geometry"])
    geometry["coordinates"][0][1][0] -= .0001
    plan = command(client, plan, "reshape", {"zone_id": zone["id"], "geometry": geometry,
                   "type_id": zone["type_id"], "policy": "preserve"})
    assert len(plan["scenarios"][1]["zones"][0]["geometry"]["coordinates"]) == 2
    geometry["coordinates"][0].pop()
    command(client, plan, "draw", {"geometry": geometry, "type_id": zone["type_id"], "policy": "replace"}, status=422)


def test_explicit_zero_controls_are_distinct_from_unknown(client, plan):
    plan = command(client, plan, "add_type", {"type": {"code": "P", "name": "Open space proposal",
                   "color": "#4d9156", "coverage": 0, "far": 0, "max_floors": 0}})
    plan = draw(client, plan)
    report = client.get(f"/api/v1/zoning/plans/{plan['id']}/indicators?scenario_id={plan['scenarios'][1]['id']}").json()
    assert report["rows"][0]["far_bound_m2"] == 0
    assert report["rows"][0]["footprint_bound_m2"] == 0
    assert plan["types"][0]["max_height"] is None
