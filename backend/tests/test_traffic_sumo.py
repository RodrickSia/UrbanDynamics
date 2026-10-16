import xml.etree.ElementTree as ET
from datetime import time
from gzip import compress
from json import dumps
from pathlib import Path
from subprocess import TimeoutExpired

import pytest
from fastapi import HTTPException

from app.routers import traffic_sumo
from app.services import traffic_sumo_prediction


class FakeEdge:
    def __init__(self, edge_id, speed, shape):
        self.edge_id = edge_id
        self.speed = speed
        self.shape = shape

    def getID(self):
        return self.edge_id

    def getSpeed(self):
        return self.speed

    def getShape(self):
        return self.shape


class FakeNetwork:
    def __init__(self):
        self.edges = [
            FakeEdge("busy", 20, [(0, 0), (1, 1)]),
            FakeEdge("empty", 15, [(1, 1), (2, 2)]),
        ]

    def getEdges(self):
        return self.edges

    def convertXY2LonLat(self, x, y):
        return x, y


class FakeConnection:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return self

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


def test_latest_endpoint_returns_the_newest_precomputed_run(monkeypatch):
    scenario = {
        "run_id": "cached-run",
        "weekday": 1,
        "period": "08:00",
        "metadata": {"simulation_model": "mesoscopic-6h-mixed-motorcycle-v1"},
        "generated_at": "2026-10-15T12:00:00Z",
    }
    monkeypatch.setattr(
        traffic_sumo.prediction, "latest_cached_scenario", lambda: scenario
    )

    response = traffic_sumo.get_latest_scenario()

    assert response["status"] == "completed"
    assert response["cached"] is True
    assert response["run_id"] == "cached-run"
    assert response["weekday"] == 1
    assert response["period"] == "08:00"


def test_latest_endpoint_returns_404_when_no_precomputed_run_exists(monkeypatch):
    monkeypatch.setattr(traffic_sumo.prediction, "latest_cached_scenario", lambda: None)

    with pytest.raises(HTTPException) as error:
        traffic_sumo.get_latest_scenario()

    assert error.value.status_code == 404


def test_sumo_run_submission_endpoint_is_not_exposed():
    assert not any(
        route.path.endswith("/runs") and "POST" in route.methods
        for route in traffic_sumo.router.routes
    )


def test_scenario_cache_endpoint_returns_cache_miss_as_404(monkeypatch):
    monkeypatch.setattr(traffic_sumo.prediction, "cached_scenario", lambda *_args: None)

    with pytest.raises(HTTPException) as error:
        traffic_sumo.get_cached_scenario(weekday=3, period="07:30")

    assert error.value.status_code == 404


def test_scenario_cache_only_returns_results_from_the_current_model(monkeypatch):
    connection = FakeConnection(result=("meso-run", {"simulation_model": "mesoscopic-6h-mixed-motorcycle-v1"}))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    cached = traffic_sumo_prediction.cached_scenario(2, "08:00")

    assert cached["run_id"] == "meso-run"
    assert connection.calls[0][1] == (2, "08:00", "mesoscopic-6h-mixed-motorcycle-v1")


def test_latest_cached_scenario_selects_only_the_current_six_hour_model(monkeypatch):
    metadata = {"simulation_model": "mesoscopic-6h-mixed-motorcycle-v1"}
    connection = FakeConnection(result=("run-id", 1, time(8, 0), metadata, "generated"))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    scenario = traffic_sumo_prediction.latest_cached_scenario()

    assert scenario == {
        "run_id": "run-id",
        "weekday": 1,
        "period": "08:00",
        "metadata": metadata,
        "generated_at": "generated",
    }
    assert connection.calls[0][1] == ("mesoscopic-6h-mixed-motorcycle-v1",)


def test_timed_out_sumo_stage_preserves_stderr_for_diagnosis(tmp_path, monkeypatch):
    monkeypatch.setattr(traffic_sumo_prediction, "_sumo_home", lambda: tmp_path)

    def timeout(*_args, **_kwargs):
        raise TimeoutExpired("sumo", 60, stderr=b"network loading diagnostic")

    monkeypatch.setattr(traffic_sumo_prediction.subprocess, "run", timeout)

    with pytest.raises(RuntimeError, match="network loading diagnostic"):
        traffic_sumo_prediction._run(["sumo"], tmp_path, 60)


def test_cached_result_is_decompressed_from_database(monkeypatch):
    result = {"type": "FeatureCollection", "features": [], "metadata": {"engine": "SUMO"}}
    connection = FakeConnection(result=(compress(dumps(result).encode("utf-8")),))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    assert traffic_sumo_prediction.read_cached_result("cached-run") == result


def test_cleanup_removes_only_the_matching_run_scratch_directory(tmp_path, monkeypatch):
    from uuid import uuid4

    run_id = str(uuid4())
    other_run = str(uuid4())
    runtime = tmp_path / "runtime"
    first = runtime / "runs" / run_id
    other = runtime / "runs" / other_run
    first.mkdir(parents=True)
    other.mkdir(parents=True)
    monkeypatch.setenv("TRAFFIC_SIMULATION_DIR", str(runtime))

    traffic_sumo_prediction.cleanup_run(run_id)

    assert not first.exists()
    assert other.is_dir()


def test_target_demand_is_fixed_minimum_and_independent_of_scenario():
    assert traffic_sumo_prediction._target_demand(1, "08:00") == (60.0, 0)
    assert traffic_sumo_prediction._target_demand(7, "23:30") == (60.0, 0)
    assert traffic_sumo_prediction.PLANNED_TOTAL_TRIPS_6H == 360
    assert traffic_sumo_prediction.PLANNED_CAR_TRIPS_6H == 108
    assert traffic_sumo_prediction.PLANNED_MOTORCYCLE_TRIPS_6H == 252


def test_batch_accepts_exactly_one_weekday_and_start_time():
    from app.services.traffic_sumo_batch import _validate_scenario

    assert _validate_scenario(3, "08:30") == time(8, 30)
    with pytest.raises(ValueError, match="weekday"):
        _validate_scenario(8, "08:30")
    with pytest.raises(ValueError, match="30-minute boundary"):
        _validate_scenario(3, "08:15")


def test_run_prediction_enables_mesoscopic_sumo(tmp_path, monkeypatch):
    network = tmp_path / "hcmc.net.xml"
    network.touch()
    sumo_home = tmp_path / "sumo"
    random_trips = sumo_home / "tools" / "randomTrips.py"
    random_trips.parent.mkdir(parents=True)
    random_trips.touch()
    commands = []
    monkeypatch.setattr(
        traffic_sumo_prediction,
        "_directories",
        lambda: (tmp_path / "data", tmp_path / "runtime"),
    )
    monkeypatch.setattr(traffic_sumo_prediction, "_network_file", lambda *_args: network)
    monkeypatch.setattr(traffic_sumo_prediction, "_target_demand", lambda *_args: (60.0, 0))
    monkeypatch.setattr(traffic_sumo_prediction, "_sumo_home", lambda: sumo_home)
    monkeypatch.setattr(
        traffic_sumo_prediction,
        "_run",
        lambda command, *_args: commands.append(command),
    )
    monkeypatch.setattr(
        traffic_sumo_prediction,
        "_features",
        lambda *_args: {"metadata": {"simulation_model": "mesoscopic-6h-mixed-motorcycle-v1"}},
    )

    result = traffic_sumo_prediction.run_prediction(1, "08:00", "scenario-test")

    sumo_command = next(command for command in commands if command[0].endswith("/sumo"))
    assert sumo_command[sumo_command.index("--mesosim") + 1] == "true"
    assert sumo_command[sumo_command.index("--end") + 1] == "21600"
    assert sumo_command[sumo_command.index("--time-to-teleport") + 1] == "300"
    trip_commands = [command for command in commands if command[1].endswith("randomTrips.py")]
    assert len(trip_commands) == 2
    trip_commands_by_mode = {command[command.index("--prefix") + 1]: command for command in trip_commands}
    assert set(trip_commands_by_mode) == {"car", "motorcycle"}
    for mode, expected_period, permission in (
        ("car", "200.0", "passenger"),
        ("motorcycle", str(21600 / 252), "motorcycle"),
    ):
        trips_command = trip_commands_by_mode[mode]
        assert trips_command[trips_command.index("--end") + 1] == "21600"
        assert trips_command[trips_command.index("--period") + 1] == expected_period
        assert trips_command[trips_command.index("--additional-file") + 1] == "vehicle-types.xml"
        assert trips_command[trips_command.index("--edge-permission") + 1] == permission
        assert trips_command[trips_command.index("--trip-attributes") + 1] == f'type="{mode}"'
        assert "--vehicle-class" not in trips_command
    duarouter_command = next(command for command in commands if command[0].endswith("/duarouter"))
    assert duarouter_command[duarouter_command.index("--route-files") + 1] == "car-trips.xml,motorcycle-trips.xml"
    vehicle_types_path = next((tmp_path / "runtime" / "runs" / "scenario-test").glob("attempt-*/vehicle-types.xml"))
    configured_types = ET.parse(vehicle_types_path).getroot().findall("vType")
    assert {item.get("id"): item.get("vClass") for item in configured_types} == {
        "car": "passenger",
        "motorcycle": "motorcycle",
    }
    additional_path = vehicle_types_path.parent / "additional.xml"
    detectors = ET.parse(additional_path).getroot().findall("edgeData")
    assert {item.get("vTypes") for item in detectors} == {"car motorcycle", "car", "motorcycle"}
    assert result["metadata"]["simulation_model"] == "mesoscopic-6h-mixed-motorcycle-v1"


def test_network_file_builds_atomically_then_reuses_runtime_cache(tmp_path, monkeypatch):
    data = tmp_path / "data"
    source = data / "osm_sumo_hcmc" / "hcmc.osm.pbf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pbf")
    runtime = tmp_path / "runtime"
    sumo_home = tmp_path / "sumo"
    type_map = sumo_home / "data" / "typemap" / "osmNetconvert.typ.xml"
    type_map.parent.mkdir(parents=True)
    type_map.touch()
    (sumo_home / "bin").mkdir()
    commands = []

    def fake_run(command, _cwd, timeout):
        commands.append((command, timeout))
        if command[0] == "osmium":
            output = Path(command[command.index("--output") + 1])
        else:
            output = Path(command[command.index("--output-file") + 1])
        output.write_text("generated")

    monkeypatch.setattr(traffic_sumo_prediction, "_sumo_home", lambda: sumo_home)
    monkeypatch.setattr(traffic_sumo_prediction, "_run", fake_run)

    network = traffic_sumo_prediction._network_file(data, runtime)
    assert network.is_file()
    assert [Path(call[0][0]).name for call in commands] == ["osmium", "netconvert"]
    assert commands[-1][1] == traffic_sumo_prediction.NETWORK_BUILD_TIMEOUT_SECONDS
    assert not list(network.parent.glob("*.building*"))

    assert traffic_sumo_prediction._network_file(data, runtime) == network
    assert len(commands) == 2


def test_feature_output_includes_zero_volume_roads_and_sums_full_period_counts():
    intervals = [
        ET.fromstring(
            '<interval begin="0" end="300"><edge id="busy" entered="2" speed="10" '
            'sampledSeconds="20" occupancy="15"/></interval>'
        ),
        ET.fromstring(
            '<interval begin="300" end="600"><edge id="busy" entered="3" speed="20" '
            'sampledSeconds="10" occupancy="30"/></interval>'
        ),
    ]
    car_intervals = [
        ET.fromstring('<interval begin="0" end="600"><edge id="busy" entered="2"/></interval>')
    ]
    motorcycle_intervals = [
        ET.fromstring('<interval begin="0" end="600"><edge id="busy" entered="3"/></interval>')
    ]

    result = traffic_sumo_prediction._features_from_intervals(
        FakeNetwork(),
        intervals,
        "run-id",
        1,
        "08:00",
        60.0,
        0,
        car_intervals=car_intervals,
        motorcycle_intervals=motorcycle_intervals,
    )

    assert len(result["features"]) == 2
    busy, empty = result["features"]
    assert busy["properties"]["simulated_vehicles_6h"] == 5
    assert busy["properties"]["simulated_cars_6h"] == 2
    assert busy["properties"]["simulated_motorcycles_6h"] == 3
    assert busy["properties"]["simulated_speed_kmh"] == 48.0
    assert empty["properties"]["simulated_vehicles_6h"] == 0
    assert empty["properties"]["simulated_speed_kmh"] == 54.0
    assert result["metadata"]["max_simulated_vehicles_6h"] == 5
    assert result["metadata"]["simulation_model"] == "mesoscopic-6h-mixed-motorcycle-v1"
    assert result["metadata"]["planned_motorcycle_trips_6h"] == 252
    assert result["metadata"]["planned_car_trips_6h"] == 108
    assert result["metadata"]["planned_total_trips_6h"] == 360
    assert result["metadata"]["simulation_duration_hours"] == 6
    assert result["metadata"]["vehicle_count_period_seconds"] == 21600
    assert result["metadata"]["vehicle_count_period_label"] == "simulated 6-hour period"
    assert result["metadata"]["simulation_interval_seconds"] == 600
