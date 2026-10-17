from copy import deepcopy

import pytest

from test_zoning import client, plan, command, rectangle, add_type, draw  # noqa: F401
from app.routers import zoning
from app.services import parcels
from app.services.zoning.geometry import projected


@pytest.fixture
def parcel_source(monkeypatch):
    monkeypatch.setattr(zoning, "warehouse_configured", lambda: True)
    source = {"id": "3885881", "land_use": "ODT", "geometry": rectangle()}
    monkeypatch.setattr(parcels, "development_parcel", lambda identifier: deepcopy(source) if identifier == 3885881 else None)
    return source


def building(**extra):
    return {"parcel_id": "3885881", "geometry": rectangle(106.7602, 10.8202, 106.7605, 10.8205),
            "floors": 2, "floor_height": 3.2, "space_use_id": "residential", **extra}


def test_zone_is_a_buildable_site_independent_of_underlying_parcels(client, plan, monkeypatch):
    from app.services.zoning import baseline
    monkeypatch.setattr(baseline, 'buildings', lambda *args: None)
    plan = draw(client, add_type(client, plan), rectangle())
    scenario = plan['scenarios'][1]
    zone = scenario['zones'][0]
    site_id = f"zone:{zone['id']}"
    response = client.get(f"/api/v1/zoning/plans/{plan['id']}/development/parcels/{site_id}",
                          params={'scenario_id': scenario['id']})
    assert response.status_code == 200, response.text
    assert response.json()['parcel']['source'] == 'scenario.zone'
    assert projected(response.json()['parcel']['geometry']).area == pytest.approx(projected(zone['geometry']).area)
    plan = command(client, plan, 'save_building', building(parcel_id=site_id))
    assert plan['scenarios'][1]['buildings'][0]['parcel_id'] == site_id
    preview(client, plan, building(parcel_id=site_id, geometry=rectangle(106.759, 10.819)), status=422)
    # Duplicating a scenario must remap the site to its own zone, not the original.
    plan = command(client, plan, 'add_scenario', {'name': 'Zone alternative'})
    clone = plan['scenarios'][-1]
    clone_id = f"zone:{clone['zones'][0]['id']}"
    assert clone['buildings'][0]['parcel_id'] == clone_id
    assert clone_id in plan['parcels']
    command(client, plan, 'save_building', building(parcel_id=site_id), clone['id'], status=422)
    command(client, plan, 'delete_zone', {'zone_id': zone['id'], 'confirm': True}, status=422)


def preview(client, plan, payload, action="save_building", status=200):
    response = client.post(f"/api/v1/zoning/plans/{plan['id']}/preview", json={
        "revision": plan["revision"], "scenario_id": plan["scenarios"][1]["id"], "action": action, "payload": payload})
    assert response.status_code == status, response.text
    return response.json()


def test_preview_metrics_and_unknown_rules(client, plan, parcel_source):
    draft = preview(client, plan, building())
    area = projected(building()["geometry"]).area
    assert draft["metrics"]["gfa_m2"] == pytest.approx(area * 2)
    assert draft["metrics"]["coverage_pct"] == pytest.approx(100 * area / projected(rectangle()).area)
    assert all(c["status"] == "UNKNOWN" and c["allowed"] is None for c in draft["checks"])
    saved = client.get(f"/api/v1/zoning/plans/{plan['id']}").json()
    assert saved["revision"] == plan["revision"]
    assert saved["scenarios"][1]["buildings"] == []


def test_persist_clone_edit_lock_undo_and_baseline_isolation(client, plan, parcel_source):
    baseline = deepcopy(plan["scenarios"][0])
    plan = command(client, plan, "save_building", building(demolish=True))
    a = deepcopy(plan["scenarios"][1])
    plan = command(client, plan, "add_scenario", {"name": "B", "description": "Independent alternative"})
    b = plan["scenarios"][-1]
    assert b["buildings"][0]["id"] != a["buildings"][0]["id"]
    assert b["buildings"][0]["origin_id"] == a["buildings"][0]["id"]
    plan = command(client, plan, "save_building", building(id=b["buildings"][0]["id"], floors=4), b["id"])
    assert plan["scenarios"][1] == a
    assert plan["scenarios"][0] == baseline
    plan = command(client, plan, "undo_development", scenario_id=b["id"])
    assert plan["scenarios"][-1]["buildings"][0]["floors"] == 2
    plan = command(client, plan, "redo_development", scenario_id=b["id"])
    assert plan["scenarios"][-1]["buildings"][0]["floors"] == 4
    plan = command(client, plan, "lock_scenario", {"locked": True}, b["id"])
    command(client, plan, "save_building", building(), b["id"], status=422)
    command(client, plan, "restore_parcel", {"parcel_id": "3885881", "confirm": True}, b["id"], status=422)
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == plan


def test_invalid_geometry_overlap_and_conflict_keep_saved_state(client, plan, parcel_source):
    command(client, plan, "save_building", building(geometry=rectangle(106.75, 10.81)), status=422)
    bowtie = {"type": "Polygon", "coordinates": [[[106.76,10.82],[106.761,10.821],[106.761,10.82],[106.76,10.821],[106.76,10.82]]]}
    command(client, plan, "save_building", building(geometry=bowtie), status=422)
    old = plan
    plan = command(client, plan, "save_building", building())
    command(client, old, "save_building", building(), status=409)
    command(client, plan, "save_building", building(), status=422)
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == plan


def test_snapshot_survives_unavailable_source_and_demolition_is_reversible(client, plan, parcel_source, monkeypatch):
    plan = command(client, plan, "demolish_parcel", {"parcel_id": "3885881", "confirm": True})
    assert len(plan["scenarios"][1]["demolition_masks"]) == 1
    monkeypatch.setattr(zoning, "warehouse_configured", lambda: False)
    plan = command(client, plan, "save_building", building())
    plan = command(client, plan, "restore_parcel", {"parcel_id": "3885881", "confirm": True})
    assert plan["scenarios"][1]["demolition_masks"] == []
    assert plan["parcels"]["3885881"]["land_use"] == "ODT"


def test_generation_uses_explicit_assumptions_and_proposal_bounds(client, plan, parcel_source):
    plan = draw(client, add_type(client, plan), rectangle())
    result = preview(client, plan, {"parcel_id": "3885881", "floors": 3, "floor_height": 3.2,
        "coverage": 30, "setback": 2}, action="generate_building")
    assert result["metrics"]["coverage_pct"] <= 30 + 1e-5
    assert result["building"]["template_version"] == 1
    assert result["building"]["ground_anchor"]["status"] == "elevation_unverified"
    assert all(c["status"] == "UNKNOWN" for c in result["checks"])
    assert next(c for c in result["checks"] if c["rule"] == "far")["assumption_status"] == "PASS"


def test_scenario_metadata_reorder_and_reference_write_rejected(client, plan, parcel_source):
    plan = command(client, plan, "add_scenario", {"name": "B", "description": "Test"})
    ids = [s["id"] for s in plan["scenarios"]]
    plan = command(client, plan, "reorder_scenarios", {"ids": [ids[0], ids[2], ids[1]]})
    assert plan["scenarios"][1]["description"] == "Test"
    command(client, plan, "save_building", building(), ids[0], status=422)
    command(client, plan, "reorder_scenarios", {"ids": list(reversed(ids))}, status=422)


def test_clone_rule_catalog_is_independent_and_locked_type_writes_rejected(client, plan):
    plan = draw(client, add_type(client, plan))
    plan = command(client, plan, "add_scenario", {"name": "B"})
    a, b = plan["scenarios"][1:]
    assert a["zones"][0]["type_id"] != b["zones"][0]["type_id"]
    comparison = client.get(f"/api/v1/zoning/plans/{plan['id']}/indicators", params={"scenario_id": b["id"], "compare_id": a["id"]}).json()
    assert comparison["changed_m2"] == pytest.approx(0, abs=.001)
    from app.services.zoning.models import ZoneType
    original = plan["types"][0]
    fields = {k: v for k, v in original.items() if k in ZoneType.model_fields}
    fields["far"] = 9
    plan = command(client, plan, "edit_type", {"id": original["id"], "type": fields})
    assert next(t for t in plan["types"] if t["id"] == b["zones"][0]["type_id"])["far"] == 4
    plan = command(client, plan, "lock_scenario", {"locked": True})
    command(client, plan, "add_type", {"type": {"code": "X", "name": "Bypass", "color": "#123456"}}, status=422)


def test_source_unavailable_and_invalid_ids_do_not_create_fake_parcels(client, plan):
    from app.services.zoning import store
    original = store.load(plan["id"])
    command(client, plan, "save_building", building(), status=503)
    command(client, plan, "save_building", building(parcel_id="-1"), status=422)
    assert store.load(plan["id"]) == original


def test_gfa_and_far_flags_do_not_double_count_or_conflate_metrics(client, plan, parcel_source):
    result = preview(client, plan, building(counts_gfa=False, counts_far=True))
    assert result["metrics"]["gfa_m2"] == 0
    assert result["metrics"]["far"] > 0
    assert result["metrics"]["footprint_m2"] > 0
    assert sum(result["metrics"]["space_use_m2"].values()) == 0


def test_mixed_use_floors_height_metrics_and_scenario_persistence(client, plan, parcel_source):
    overrides = [
        {"floor": 1, "space_use_id": "commercial", "floor_height": 4.5, "counts_gfa": True, "counts_far": True},
        {"floor": 3, "space_use_id": "other", "floor_height": 2.5, "counts_gfa": False, "counts_far": False},
    ]
    payload = building(floors=3, floor_overrides=overrides)
    result = preview(client, plan, payload)
    area = projected(payload["geometry"]).area
    assert result["building"]["height_m"] == pytest.approx(10.2)
    stack = result["building"]["floor_stack"]
    assert [f["base_m"] for f in stack] == pytest.approx([0, 4.5, 7.7])
    assert [f["top_m"] for f in stack] == pytest.approx([4.5, 7.7, 10.2])
    assert [f["color"] for f in stack] == ["#C18EAD", "#D79B8C", "#8CA6AD"]
    assert result["metrics"]["gfa_m2"] == pytest.approx(area * 2)
    assert result["metrics"]["far"] == pytest.approx(area * 2 / projected(rectangle()).area)
    assert result["metrics"]["coverage_pct"] == pytest.approx(100 * area / projected(rectangle()).area)
    assert result["metrics"]["space_use_m2"] == pytest.approx({"commercial": area, "residential": area, "office": 0, "school": 0, "other": 0})
    plan = command(client, plan, "save_building", payload)
    original = deepcopy(plan["scenarios"][1]["buildings"][0])
    plan = command(client, plan, "add_scenario", {"name": "Mixed-use alternative"})
    clone = plan["scenarios"][-1]
    plan = command(client, plan, "save_building", building(id=clone["buildings"][0]["id"], floors=3), clone["id"])
    assert plan["scenarios"][1]["buildings"][0] == original
    plan = command(client, plan, "undo_development", scenario_id=clone["id"])
    reloaded = client.get(f"/api/v1/zoning/plans/{plan['id']}").json()
    assert reloaded["scenarios"][-1]["buildings"][0]["floor_overrides"] == overrides


@pytest.mark.parametrize("overrides", [
    [{"floor": 0}], [{"floor": 3}], [{"floor": 1}, {"floor": 1}],
    [{"floor": 1, "floor_height": 0}], [{"floor": 1, "space_use_id": "invented"}],
])
def test_invalid_floor_override_rejected_without_mutation(client, plan, parcel_source, overrides):
    floors = [{"space_use_id": "commercial", "floor_height": 4, "counts_gfa": True, "counts_far": True, **o} for o in overrides]
    command(client, plan, "save_building", building(floor_overrides=floors), status=422)
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == plan
