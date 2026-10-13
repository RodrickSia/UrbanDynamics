import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation.integrated.background import publish
from app.services.simulation.planning import system_demo, store
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.jobs import process_one
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import rectangle


@pytest.fixture
def installed(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SYSTEM_DEMO_ENABLED", "1")
    monkeypatch.setenv("PLANNING_SYSTEM_SNAPSHOT_DIR", str(tmp_path/"snapshots"))
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"store.sqlite"))
    site = rectangle(106.758, 10.82)
    doc = {"schema_version": 1, "captured_at": "2026-10-12T02:00:00Z",
           "bbox": [106.75, 10.81, 106.77, 10.83], "sources": {"population": {"kind": "worldpop_estimate"}},
           "parcels": {"features": [{"type": "Feature", "id": 1, "properties": {"thua": "42"},
               "geometry": {"type": "MultiPolygon", "coordinates": [site["coordinates"]]}}]},
           "population": {"statistics": {"population_sum": 2500.5}}, "layers": {}, "osm": {"elements": []}}
    identifier = publish(doc, tmp_path/"snapshots")
    return identifier, doc


def payload(identifier):
    return system_demo.prepare(system_demo.Prepare(snapshot_id=identifier, parcel_ids=["1"]))


def test_demo_gate_and_no_production_study_bypass(installed, monkeypatch):
    study = payload(installed[0])
    monkeypatch.delenv("PLANNING_SYSTEM_DEMO_ENABLED")
    with TestClient(app) as client:
        assert client.get("/api/v1/planning/demo/system/snapshots").status_code == 404
        assert client.post("/api/v1/planning/demo/system/prepare", json={"snapshot_id": installed[0], "parcel_ids": ["1"]}).status_code == 404
        assert client.post("/api/v1/planning/studies", json=study).status_code == 422


def test_sourced_geometry_inclusive_population_unknown_capacity_and_frozen_context(installed):
    study = PlanningStudy(**payload(installed[0]))
    original = copy.deepcopy(study.model_dump())
    context = build_context(study)
    assert context["source_kind"] == context["source_manifest"]["source_kind"] == "mixed_demo"
    assert context["system_background"]["snapshot_id"] == installed[0]
    assert context["system_background"]["parcel_bindings"] == {"P1": "1"}
    assert context["system_background"]["planning_review"][0]["legal_approval_established"] is False
    assert context["system_background"]["selected_parcels"][0]["properties"]["thua"] == "42"
    sources = {entry["id"]: entry for entry in context["source_manifest"]["entries"]}
    assert sources["parcel_geometry"]["source_kind"] == "team_sourced_geometry"
    assert sources["regional_population"]["source_kind"] == "estimated"
    assert sources["traffic_background"]["source_kind"] == "unknown"
    assert study.background_residents == 2500
    result = run_screening(study)
    assert result["baseline"]["baseline_ledger"]["background_basis"] == "inclusive_population_prior_unresolved"
    row = next(r for r in result["options"][0]["comparison"] if r["metric"] == "power_peak_kw")
    assert row["delta"] is None and row["comparability"] == "insufficient_data"
    assert all(c["status"] == "unknown" for c in result["options"][0]["state"]["utility_zones"][0]["checks"])
    assert study.model_dump() == original
    assert build_context(PlanningStudy(**context["inputs"])) == context


def test_rejects_wrong_parcel_geometry_id_and_snapshot_tampering(installed):
    with pytest.raises(ValueError, match="eligible"):
        system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0], parcel_ids=["999"]))
    p = payload(installed[0])
    p["projects"][0]["site"] = rectangle(106.76, 10.82)
    # Match a replacement plan too, so schema geometry validation passes.
    from app.services.simulation.engine import polygon_and_area
    from app.services.simulation.models import PolygonInput
    area = polygon_and_area(PolygonInput(**p["projects"][0]["site"]))[1]
    p["projects"][0]["baseline"] = {"green_m2": area}
    p["projects"][0]["development"] = {"green_m2": area}
    with pytest.raises(ValueError, match="does not match"):
        build_context(PlanningStudy(**p))
    path = system_demo.directory()/(installed[0]+".json")
    path.write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        system_demo.load(installed[0])


def test_multipart_parcel_not_silently_reduced_and_api_worker_preserves_source(installed):
    doc = copy.deepcopy(installed[1])
    doc["parcels"]["features"][0]["geometry"]["coordinates"].append(rectangle(106.761, 10.82)["coordinates"])
    assert system_demo.candidates(doc) == []
    with TestClient(app) as client:
        response = client.post("/api/v1/planning/demo/system/prepare", json={"snapshot_id": installed[0], "parcel_ids": ["1"]})
        assert response.status_code == 200
        created = client.post("/api/v1/planning/studies", json=response.json()["study"])
        assert created.status_code == 201
        job = client.post(f"/api/v1/planning/studies/{created.json()['id']}/runs", json={"mode": "screening", "idempotency_key": "system-demo-frozen"})
        assert job.status_code == 202
        done = process_one()
        assert done["status"] == "succeeded", done
        result = store.load_document(done["result_id"], "run")
        assert result["context"]["system_background"]["snapshot_id"] == installed[0]
        collection = client.get(f"/api/v1/planning/runs/{done['result_id']}/map", params={"name": "parcels", "option_id": "P1_only"}).json()
        assert collection["source_kind"] == "mixed_demo"
        assert "system_snapshot" in collection["features"][0]["properties"]["source_ids"]


def test_equal_program_and_cumulative_groups_on_different_parcels(installed):
    doc = copy.deepcopy(installed[1])
    doc["parcels"]["features"] += [{"type": "Feature", "id": str(i), "properties": {},
        "geometry": rectangle(106.758+i*.002, 10.82)} for i in (2,3)]
    identifier = publish(doc, system_demo.directory())
    equal = PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=identifier,
        parcel_ids=["1","2","3"], equal_program=True, floor_area_m2=1600)))
    result = run_screening(equal)
    assert equal.comparison_policy == "equal_program"
    assert {sum(b.gross_floor_area_m2 for b in p.development.buildings) for p in equal.projects} == {1600}
    assert len(result["options"]) == 3
    cumulative = PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=identifier,
        parcel_ids=["1","2","3"], mode="cumulative", floor_area_m2=1600,
        programs={"2": system_demo.BuildingProgram(housing_units=30,residents=90,floors=6,floor_area_m2=2400)})))
    result = run_screening(cumulative)
    assert len(result["options"]) == 5
    assert cumulative.phases[-1].active_project_ids == ["P1","P2","P3"]
    all_built = next(o for o in result["options"] if o["id"] == "together_3")
    assert all_built["state"]["metrics"]["housing_units"] == 70
    assert all_built["state"]["metrics"]["floor_area_m2"] == pytest.approx(5600)
    assert build_context(cumulative)["system_background"]["parcel_bindings"] == {"P1":"1","P2":"2","P3":"3"}
    custom = system_demo.prepare(system_demo.Prepare(snapshot_id=identifier,parcel_ids=["1","2","3"],
        mode="cumulative",scenario_parcels=[["1","3"],["2","3"]]))
    assert custom["options"][0]["active_project_ids"] == ["P1","P3"]


def test_rejects_unfair_program_and_invalid_scenario_groups(installed):
    with pytest.raises(ValueError, match="explicit floor area"):
        system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=["1"],equal_program=True))
    with pytest.raises(ValueError, match="Scenario groups"):
        system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=["1"],mode="cumulative",scenario_parcels=[["1","999"]]))
    with pytest.raises(ValueError, match="80 percent"):
        system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=["1"],floors=1,floor_area_m2=40000))


def test_counting_reference_supports_mix_prior_not_observed_site_od(installed):
    from app.services.simulation.planning.counting_reference import directory,load
    doc={'schema_version':'traffic-counts-identity-repair-1','simulation_ready':False,
         'camera_id':'UIT historical clip','source_sha256':'a'*64,'tracks_sha256':'b'*64,
         'observation':{'duration_seconds':16.6666667},'repaired_crossings':15,
         'counts':[{'vehicle_class':'car','count':1},{'vehicle_class':'motorcycle','count':13},{'vehicle_class':'bus','count':1}]}
    raw=json.dumps(doc,sort_keys=True).encode();identifier=hashlib.sha256(raw).hexdigest()
    directory().mkdir();(directory()/(identifier+'.json')).write_bytes(raw)
    study=PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=['1'],
        counting_reference_id=identifier,traffic_peak_vehicles_hour=800)))
    assert study.traffic_prior.source_kind=='estimated'
    context=build_context(study)
    assert context['resolved_background']['traffic']['cars'][18]==57
    assert context['resolved_background']['traffic']['motorcycles'][18]==743
    assert context['system_background']['counting_reference']['simulation_ready'] is False
    assert any(x['id']=='counting_reference' for x in context['source_manifest']['entries'])
    assert context['data_coverage']['observed_camera_counts'] is False
    assert study.projects[0].baseline_occupancy=='unknown'
    (directory()/(identifier+'.json')).write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        load(identifier)


def test_source_planning_labels_flag_housing_conflicts_without_legal_pass(installed):
    doc=copy.deepcopy(installed[1]);doc['parcels']['features'][0]['properties'].update(
        mdsdd='DSK',loai_dat_qh='Đất cây xanh cảnh quan: 500 m2; Đất giao thông: 200 m2')
    identifier=publish(doc,system_demo.directory())
    context=build_context(PlanningStudy(**payload(identifier)))
    review=context['system_background']['planning_review'][0]
    assert review['status']=='potential_conflict'
    assert review['legal_approval_established'] is False
    assert review['permitted_far'] is None
    assert len(review['flags'])==2


def test_landcover_provenance_and_osm_access_without_capacity_are_frozen(installed):
    doc=copy.deepcopy(installed[1])
    site=doc["parcels"]["features"][0]["geometry"]
    doc["landcover"]={"type":"FeatureCollection","features":[{"type":"Feature", "geometry":site,
        "properties":{"class_code":30}}],"metadata":{"dataset":"ESA WorldCover 2021 v200","year":2021}}
    doc["osm"]={"elements":[{"type":"way","id":7,"nodes":[1,2],"tags":{"highway":"residential"},
        "geometry":[{"lon":106.758,"lat":10.82},{"lon":106.760,"lat":10.82}]},
        {"type":"node","id":8,"lon":106.760,"lat":10.82,"tags":{"amenity":"school"}}]}
    identifier=publish(doc,system_demo.directory())
    study=PlanningStudy(**payload(identifier))
    result=run_screening(study)
    context=result["context"]
    quality=context["system_background"]["baseline_reconstruction"]["P1"]
    assert quality["matches_source_reconstruction"]
    assert quality["provenance"]["mapped_green_m2"]>0
    assert context["system_background"]["landcover"]["year"]==2021
    sources={s["id"]:s for s in context["source_manifest"]["entries"]}
    assert sources["historical_landcover"]["source_kind"]=="historical_classification"
    assert sources["walking_network"]["source_kind"]=="mixed_sourced_inputs"
    service=result["options"][0]["state"]["school_services"]
    assert service["walking_method"]=="osm_shortest_foot_path_with_estimated_connectors"
    assert service["metrics"]["school_unserved_students"] is None
    routes=[f for f in service["map"]["features"] if f["geometry"]["type"]=="LineString"]
    assert routes and all(f["properties"]["students"] is None for f in routes)
    assert all(f["properties"]["network_distance_m"]>0 for f in routes)
    assert build_context(PlanningStudy(**context["inputs"]))==context


def test_fixed_osm_neighbours_and_trees_shared_across_options(installed):
    doc=copy.deepcopy(installed[1])
    polygon=rectangle(106.7594,10.82)
    doc["osm"]={"elements":[{"type":"way","id":9,"tags":{"building":"yes","height":"24"},
        "geometry":[{"lon":x,"lat":y} for x,y in polygon["coordinates"][0]]},
        {"type":"node","id":10,"lon":106.7593,"lat":10.82,"tags":{"natural":"tree"}}]}
    identifier=publish(doc,system_demo.directory())
    study=PlanningStudy(**payload(identifier))
    result=run_screening(study)
    fixed=result["context"]["fixed_solar_context"]
    assert len(fixed["features"])==2
    building=next(f for f in fixed["features"] if f["geometry"]["type"]!="Point")
    assert building["properties"]["height_m"]==24
    tree=next(f for f in fixed["features"] if f["geometry"]["type"]=="Point")
    assert tree["properties"]["provenance"]["height"]=="synthetic_default"
    baseline=result["baseline"]["shadow"]
    assert baseline["metrics"]["mean_shaded_receiver_m2"]>0
    for option in result["options"]:
        assert option["state"]["shadow"]["fixed_context"]==fixed
        assert option["state"]["shadow"]["receiver_area_m2"]==baseline["receiver_area_m2"]
    assert build_context(PlanningStudy(**result["context"]["inputs"]))==result["context"]
