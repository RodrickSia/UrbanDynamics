from pathlib import Path
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.native import run_native


@pytest.fixture(scope="module")
def native_portfolio(tmp_path_factory):
    root = tmp_path_factory.mktemp("planning-native")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SIMULATION_WORK_DIR", str(root))
        payload = demo_study("cumulative")
        payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
        yield run_native(PlanningStudy(**payload)), root


def test_native_shared_network_phase_identity_and_conservation(native_portfolio):
    result, root = native_portfolio
    assert all(result["validity"].values())
    assert result["unique_states_evaluated"] == 6
    options = {option["id"]: option for option in result["options"]}
    assert result["phases"][2]["state"] == options["ABC"]["state"]
    assert result["phases"][1]["state"] == options["AB"]["state"]
    baseline = result["baseline"]["traffic"]["runs"][0]
    after = options["ABC"]["state"]["traffic"]["runs"][0]
    assert baseline["planned_vehicles"] == 400
    assert after["planned_vehicles"] > baseline["planned_vehicles"]
    assert after["planned_vehicles"] == after["completed_vehicles"]+after["unfinished_vehicles"]+after["undeparted_vehicles"]
    assert "background_completed_delay_seconds" in after
    assert all(row["hour_local"] == 18 for row in options["ABC"]["traffic_comparison"])
    network = ET.parse(root/result["network_artifacts"]["artifact_id"]/"network.xml").getroot()
    from app.services.simulation.planning.network import specification
    physical_ids = specification(PlanningStudy(**{**demo_study("cumulative"), "conditions": {"traffic_hours": [18], "seeds": [2026]}}))["project_to_solver_parcel"]
    assert all(network.find(f"edge[@id='{physical_ids[identifier]}_in']") is not None for identifier in ("A", "B", "C"))


def test_background_departure_streams_unchanged_and_no_private_shortcuts(native_portfolio):
    result, root = native_portfolio
    runs = [result["baseline"]["traffic"]["runs"][0]]+[o["state"]["traffic"]["runs"][0] for o in result["options"]]
    streams = []
    for run in runs:
        routes = ET.parse(root/run["artifacts"]["artifact_id"]/"routes.xml").getroot()
        streams.append([(v.get("id"), v.get("depart"), v.get("route")) for v in routes.findall("vehicle") if v.get("id").startswith("background_")])
        for route in routes.findall("route"):
            if route.get("id").startswith("background_"):
                assert all(edge.startswith("road_") for edge in route.get("edges").split())
    assert all(stream == streams[0] for stream in streams)


def test_spatial_timeseries_match_real_solver_outputs(native_portfolio):
    from app.services.simulation.planning.map_output import layer
    result, root = native_portfolio
    combined = next(o for o in result["options"] if o["id"] == "ABC")["state"]
    run = combined["traffic"]["runs"][0]
    queues = ET.parse(root/run["artifacts"]["artifact_id"]/"queues.xml").getroot()
    network = ET.parse(root/run["artifacts"]["artifact_id"]/"network.xml").getroot()
    lanes = {lane.get("id"): edge.get("id") for edge in network.findall("edge") for lane in edge.findall("lane")}
    interval = next(i for i, q in enumerate(run["queue_intervals"]) if q["edges"])
    sample = run["queue_intervals"][interval]
    expected = {}
    for step in queues:
        if sample["begin_seconds"] <= float(step.get("timestep")) < sample["end_seconds"]:
            for lane in step.iter("lane"):
                edge = lanes[lane.get("id")]
                expected[edge] = max(expected.get(edge, 0), float(lane.get("queueing_length")))
    roads = layer(result, "ABC", "roads", hour=18, seed=2026, interval=interval)
    for feature in roads["features"]:
        props = feature["properties"]
        assert props["sampled_peak_queue_m"] == expected.get(props["edge_id"])
        assert "sampled_peak_queue_m" in props["units"]
    drainage = combined["drainage"]["catchments"][0]
    sample_index = 20
    nodes = layer(result, "ABC", "drainage", drainage_sample=sample_index)
    links = layer(result, "ABC", "drainage_links", drainage_sample=sample_index)
    for feature in nodes["features"]:
        props = feature["properties"]
        assert props["depth_m"] == drainage["timeseries"]["nodes"][props["id"]]["depth_m"][sample_index]
        assert props["minute"] == drainage["timeseries"]["minute"][sample_index]
    assert links["features"]
    for feature in links["features"]:
        props = feature["properties"]
        assert feature["geometry"]["type"] == "LineString"
        assert props["flow_m3_s"] == drainage["timeseries"]["links"][props["link_id"]]["flow_m3_s"][sample_index]
        assert props["source_ids"] and props["engine"] == "SWMM"
    with pytest.raises(KeyError):
        layer(result, "ABC", "drainage_links", drainage_sample=9999)
    with pytest.raises(KeyError):
        layer(result, "ABC", "roads", hour=18, interval=-1)
    with pytest.raises(KeyError):
        layer(result, "ABC", "roads", hour=18, drainage_sample=20)
    # Repeated selectors must not mutate the immutable aggregate map.
    assert "depth_m" not in drainage["map"]["features"][0]["properties"]


def test_chunked_series_matches_native_data_and_api(native_portfolio, tmp_path, monkeypatch):
    from app.services.simulation.planning.series_output import series
    from app.services.simulation.planning import store
    from fastapi.testclient import TestClient
    from app.main import app
    result, _ = native_portfolio
    untouched = deepcopy(result)
    state = next(o["state"] for o in result["options"] if o["id"] == "ABC")
    catchment = state["drainage"]["catchments"][0]
    identifier = next(iter(catchment["timeseries"]["links"]))
    cid = catchment["catchment_id"]
    chunks, offset = [], 0
    while offset is not None:
        chunk = series(result, "phase_3", "drainage_links", identifier, offset, 37, catchment_id=cid)
        chunks.extend(chunk["samples"])
        assert len(chunk["samples"]) <= 37
        assert chunk["phase_id"] == "phase_3" and chunk["source_ids"]
        offset = chunk["pagination"]["next_offset"]
    assert [s["minute"] for s in chunks] == catchment["timeseries"]["minute"]
    assert [s["values"]["flow_m3_s"] for s in chunks] == catchment["timeseries"]["links"][identifier]["flow_m3_s"]
    runoff = series(result, "ABC", "runoff", cid, limit=300, catchment_id=cid)
    assert [s["values"]["runoff_m3_s"] for s in runoff["samples"]] == catchment["timeseries"]["runoff_m3_s"]
    traffic = state["traffic"]["runs"][0]
    road_id = result["spatial_artifacts"]["roads"]["features"][0]["properties"]["edge_id"]
    roads = series(result, "ABC", "roads", road_id, offset=1, limit=2, hour=18, seed=2026)
    for sample in roads["samples"]:
        source = traffic["edge_intervals"][sample["sample_index"]]
        edge = next((e for e in source["edges"] if e["edge_id"] == road_id), None)
        assert sample["values"]["speed"] == (edge.get("speed") if edge else None)
        queue = next((e for e in traffic["queue_intervals"][sample["sample_index"]]["edges"] if e["edge_id"] == road_id), None)
        assert sample["values"]["sampled_peak_queue_m"] == (queue["sampled_peak_queue_m"] if queue else None)
    assert result == untouched
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"series.sqlite"))
    saved = store.save_study(result["inputs"], result["context"]["sha256"])
    store.enqueue(saved["id"], "native", "series-existing-native")
    done = store.finish(store.claim(), result=result)
    client = TestClient(app)
    url = f"/api/v1/planning/runs/{done['result_id']}/timeseries"
    params = {"name": "drainage_links", "object_id": identifier, "catchment_id": cid, "option_id": "ABC", "offset": 20, "limit": 10}
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    assert response.json()["samples"][0]["minute"] == catchment["timeseries"]["minute"][20]
    for changed in ({"limit": 301}, {"offset": -1}, {"object_id": "missing"}, {"catchment_id": "missing"}, {"seed": 2026}, {"offset": 99999}, {"case_id": "missing"}):
        assert client.get(url, params={**params, **changed}).status_code == 422
    modified = deepcopy(result)
    modified["baseline"].pop("drainage")
    from app.services.simulation.planning.map_output import LayerUnavailable
    with pytest.raises(LayerUnavailable, match="native"):
        series(modified, "baseline", "drainage", "J0", catchment_id=cid)
    modified = deepcopy(result)
    altered = next(o["state"] for o in modified["options"] if o["id"] == "ABC")
    altered["traffic"]["runs"][0]["edge_intervals"][1]["edges"] = []
    altered["traffic"]["runs"][0]["queue_intervals"][1]["edges"] = []
    missing = series(modified, "ABC", "roads", road_id, offset=1, limit=1, hour=18, seed=2026)
    assert all(v is None for v in missing["samples"][0]["values"].values())
    assert missing["samples"][0]["sample_status"] == "no_reported_sample"


def test_invalid_native_rows_use_contract_comparability_and_block_ranking(native_portfolio):
    from app.services.simulation.planning.native import _pair_traffic, _pair_drainage
    from app.services.simulation.planning.comparison import rank
    result, _ = native_portfolio
    body = deepcopy(result)
    state = body["options"][0]["state"]
    state["traffic"]["runs"][0]["completed_fraction"] = .5
    rows = _pair_traffic(body["baseline"], state, body["context"]["sha256"])
    delay = [r for r in rows if r["metric"].endswith("delay_seconds")]
    assert all(r["comparability"] == "insufficient_data" and r["comparability_reason"] == "incomplete_trip_bias" for r in delay)
    body["options"][0]["traffic_comparison"] = rows
    study = PlanningStudy(**{**result["inputs"], "criteria": [{"metric": "background_completed_delay_seconds", "direction": "minimize"}]})
    assert rank(study, body)["status"] == "insufficient_data"
    state["drainage"]["balance_passed"] = False
    assert all(r["comparability"] == "not_comparable" and r["comparability_reason"] == "invalid_solver_balance"
               for r in _pair_drainage(body["baseline"], state, body["context"]["sha256"]))
    baseline = deepcopy(body["baseline"])
    baseline["baseline_occupancy_unknown"] = True
    unknown_rows = _pair_traffic(baseline, state, body["context"]["sha256"])
    assert all(r["before"] is r["after"] is r["delta"] is None and r["scenario_values"] for r in unknown_rows)
    # Re-finalize actual native states with an invalid standalone, while AB
    # itself remains valid. The published interaction must respect both runs.
    from app.services.simulation.planning.native import finalize
    body = deepcopy(result)
    states = {(): body["baseline"]}
    for option in body["options"]+body["phases"]:
        states[tuple(option["state"]["active_project_ids"])] = option["state"]
    states[("A",)]["drainage"]["balance_passed"] = False
    finalized = finalize(PlanningStudy(**body["inputs"]), body, states,
                         {"map": body["spatial_artifacts"]["roads"], "artifacts": body["network_artifacts"]})
    effect = next(item for item in finalized["interaction_effects"] if item["active_project_ids"] == ["A", "B"])
    assert effect["metrics"]["node_flooding_m3"] is None
    assert effect["comparability_by_metric"]["node_flooding_m3"] == "not_comparable"
    assert effect["scenario_values"]["node_flooding_m3"]["value"] is not None


def test_swmm_shared_nodes_background_once_and_interactions(native_portfolio):
    result, root = native_portfolio
    combined = next(o for o in result["options"] if o["id"] == "ABC")["state"]
    native = combined["drainage"]["catchments"][0]
    assert native["balance_passed"]
    assert native["background_area_m2"] == 20000
    samples = len(native["timeseries"]["minute"])
    assert native["timeseries"]["sample_interval_seconds"] == 60
    assert native["timeseries"]["nodes"] and native["timeseries"]["links"]
    assert all(len(series) == samples for item in native["timeseries"]["nodes"].values() for series in item.values())
    assert all(len(series) == samples for item in native["timeseries"]["links"].values() for series in item.values())
    inp = (root/native["artifacts"]["artifact_id"]/"drainage.inp").read_text()
    assert inp.count("background R1") == 1
    assert all(f"C_{p} J_{p} J0" in inp for p in ("A", "B", "C"))
    assert all(f"J_{p}" in {node["id"] for node in native["nodes"]} for p in ("A", "B", "C"))
    effect = next(e for e in result["interaction_effects"] if e["active_project_ids"] == ["A", "B", "C"])
    assert abs(effect["metrics"]["node_flooding_m3"]) > .001
    assert combined["metrics"]["runoff_peak_m3_s"] == max(combined["drainage"]["combined_runoff_m3_s"])
    marginal = result["marginal_effects"][1]
    before = result["phases"][0]["state"]
    after = result["phases"][1]["state"]
    assert marginal["drainage_rows"]
    for row in marginal["drainage_rows"]:
        assert row["before"] == before["metrics"][row["metric"]]
        assert row["after"] == after["metrics"][row["metric"]]
        assert row["delta"] == row["after"]-row["before"]
    for option in result["options"]:
        normalized = next(r for r in option["normalized_comparison"] if r["metric"] == "node_flooding_m3")
        assert normalized["value"] == pytest.approx((option["state"]["metrics"]["node_flooding_m3"]-result["baseline"]["metrics"]["node_flooding_m3"])/option["declared_program"]["values"]["floor_area_m2"])
        for row in option["comparison"]+option["traffic_comparison"]+option["drainage_comparison"]:
            assert all(row.get(key) for key in ("method", "unit", "time_window", "spatial_scope", "context_hash", "source_kind", "limitations"))


def test_native_three_parcel_rename_preserves_physical_results(native_portfolio, monkeypatch, tmp_path):
    original, _ = native_portfolio
    payload = demo_study("cumulative")
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    renamed = {"A": "Zulu", "B": "Yankee", "C": "Xray"}
    for project in payload["projects"]:
        project["id"] = renamed[project["id"]]
    payload["projects"].reverse()
    for option in payload["options"]+payload["phases"]:
        option["active_project_ids"] = [renamed[key] for key in reversed(option["active_project_ids"])]
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    changed = run_native(PlanningStudy(**payload))
    old_states = [original["baseline"]]+[o["state"] for o in original["options"]]
    new_states = [changed["baseline"]]+[o["state"] for o in changed["options"]]
    for before, after in zip(old_states, new_states):
        for metric, value in before["metrics"].items():
            assert after["metrics"][metric] == pytest.approx(value, abs=1e-6) if value is not None else after["metrics"][metric] is None, metric
        left, right = before["traffic"]["runs"][0], after["traffic"]["runs"][0]
        for key in ("planned_vehicles", "completed_vehicles", "unfinished_vehicles", "undeparted_vehicles",
                    "mean_completed_delay_seconds", "background_completed_delay_seconds", "max_queue_length_m"):
            assert right[key] == pytest.approx(left[key], abs=1e-6), key
        assert before["drainage"]["combined_runoff_m3_s"] == pytest.approx(after["drainage"]["combined_runoff_m3_s"], abs=1e-6)


def test_same_parcel_native_alternatives_share_access_and_drainage(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    payload = demo_study()
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    payload["projects"] = [payload["projects"][0], {**deepcopy(payload["projects"][0]), "id": "B"}]
    payload["projects"][1]["site"]["coordinates"][0].reverse()
    payload["options"] = payload["options"][:2]
    result = run_native(PlanningStudy(**payload))
    first, second = [option["state"] for option in result["options"]]
    traffic_a, traffic_b = first["traffic"]["runs"][0], second["traffic"]["runs"][0]
    for key in ("planned_vehicles", "completed_vehicles", "unfinished_vehicles", "undeparted_vehicles",
                "mean_completed_delay_seconds", "max_queue_length_m", "cohorts", "edge_intervals"):
        assert traffic_a[key] == traffic_b[key], key
    assert traffic_a["network_provenance"]["private_accesses"] == 1
    assert traffic_a["network_provenance"]["project_to_physical_parcel"] == {"A": "A", "B": "A"}
    from app.services.simulation.planning.map_output import layer
    private = [f for f in layer(result, "B_only", "roads", hour=18)["features"] if f["properties"]["private"]]
    assert private and all(f["properties"]["project_id"] == "B" for f in private)
    assert all(f["properties"]["project_ids"] == ["A", "B"] for f in private)
    edges = ET.parse(tmp_path/result["network_artifacts"]["artifact_id"]/"edges.xml").getroot()
    assert len([edge for edge in edges if edge.get("id").endswith(("_in", "_out"))]) == 2
    swmm_a, swmm_b = first["drainage"]["catchments"][0], second["drainage"]["catchments"][0]
    assert swmm_a["timeseries"] == swmm_b["timeseries"]
    assert swmm_a["nodes"] == swmm_b["nodes"]
    assert swmm_a["node_flooding_m3"] == swmm_b["node_flooding_m3"]

    # Adding a duplicate design must not alter signal phases, congestion or
    # background drainage compared with the very same single-parcel context.
    payload["projects"] = payload["projects"][:1]
    payload["options"] = payload["options"][:1]
    single = run_native(PlanningStudy(**payload))
    for state_a, state_b in ((result["baseline"], single["baseline"]),
                             (first, single["options"][0]["state"])):
        for key in ("mean_completed_delay_seconds", "max_queue_length_m", "cohorts", "edge_intervals"):
            assert state_a["traffic"]["runs"][0][key] == state_b["traffic"]["runs"][0][key]
        assert state_a["drainage"]["catchments"][0]["timeseries"] == state_b["drainage"]["catchments"][0]["timeseries"]
