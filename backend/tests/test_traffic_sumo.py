import xml.etree.ElementTree as ET
from datetime import time
from gzip import compress
from json import dumps

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


def test_submit_requires_a_half_hour_time():
    with pytest.raises(HTTPException, match="30-minute boundary") as error:
        traffic_sumo.create_run(traffic_sumo.RunRequest(weekday=1, period=time(8, 15)))
    assert error.value.status_code == 422


def test_submit_queues_a_separate_sumo_run(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(traffic_sumo.prediction, "catalog", lambda: {"available": True})
    monkeypatch.setattr(traffic_sumo, "connect_to_warehouse", lambda: connection)
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    response = traffic_sumo.create_run(traffic_sumo.RunRequest(weekday=2, period=time(8, 30)))

    assert response["status"] == "queued"
    insert = next(
        call for call in connection.calls if "INSERT INTO transport.sumo_congestion_run" in call[0]
    )
    assert insert[1][1:] == (2, time(8, 30))


def test_precomputed_scenario_is_returned_without_queueing(monkeypatch):
    monkeypatch.setattr(
        traffic_sumo.prediction,
        "cached_scenario",
        lambda _weekday, _period: {"run_id": "cached-run", "metadata": {"features": 20}},
    )

    response = traffic_sumo.create_run(traffic_sumo.RunRequest(weekday=5, period=time(17, 0)))

    assert response["status"] == "completed"
    assert response["cached"] is True
    assert response["run_id"] == "cached-run"


def test_scenario_cache_endpoint_returns_cache_miss_as_404(monkeypatch):
    monkeypatch.setattr(traffic_sumo.prediction, "cached_scenario", lambda *_args: None)

    with pytest.raises(HTTPException) as error:
        traffic_sumo.get_cached_scenario(weekday=3, period="07:30")

    assert error.value.status_code == 404


def test_cached_result_is_decompressed_from_database(monkeypatch):
    result = {"type": "FeatureCollection", "features": [], "metadata": {"engine": "SUMO"}}
    connection = FakeConnection(result=(compress(dumps(result).encode("utf-8")),))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    assert traffic_sumo_prediction.read_cached_result("cached-run") == result


def test_target_demand_uses_historical_los_as_a_prior_not_a_vehicle_count(monkeypatch):
    connection = FakeConnection(result=(3.0, 25))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    period, rows = traffic_sumo_prediction._target_demand(1, "08:00")

    assert period == pytest.approx(2.94)
    assert rows == 25
    assert "avg(CASE los" in connection.calls[0][0]


def test_target_demand_falls_back_to_weekday_or_network_history(monkeypatch):
    connection = FakeConnection(result=(2.5, 85))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    trip_period, rows = traffic_sumo_prediction._target_demand(7, "23:30")

    assert trip_period == pytest.approx(3.25)
    assert rows == 85
    assert "weekday_periods AS" in connection.calls[0][0]
    assert "all_periods AS" in connection.calls[0][0]


def test_batch_enumerates_every_weekday_and_half_hour():
    from app.services.traffic_sumo_batch import PERIODS, SCENARIO_COUNT, WEEKDAYS

    assert len(WEEKDAYS) * len(PERIODS) == SCENARIO_COUNT == 336
    assert PERIODS[0] == time(0, 0)
    assert PERIODS[-1] == time(23, 30)


def test_feature_output_includes_zero_car_roads_and_sums_full_period_counts():
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

    result = traffic_sumo_prediction._features_from_intervals(
        FakeNetwork(), intervals, "run-id", 1, "08:00", 3.0, 25
    )

    assert len(result["features"]) == 2
    busy, empty = result["features"]
    assert busy["properties"]["estimated_cars_30min"] == 5
    assert busy["properties"]["simulated_speed_kmh"] == 48.0
    assert empty["properties"]["estimated_cars_30min"] == 0
    assert empty["properties"]["simulated_speed_kmh"] == 54.0
    assert result["metadata"]["max_estimated_cars_30min"] == 5
    assert result["metadata"]["simulation_interval_seconds"] == 600
