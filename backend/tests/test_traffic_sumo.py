from datetime import time

import pytest
from fastapi import HTTPException

from app.routers import traffic_sumo
from app.services import traffic_sumo_prediction


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

    response = traffic_sumo.create_run(traffic_sumo.RunRequest(weekday=2, period=time(8, 30)))

    assert response["status"] == "queued"
    assert connection.calls[0][1][1:] == (2, time(8, 30))
    assert "transport.sumo_congestion_run" in connection.calls[0][0]


def test_target_demand_uses_historical_los_as_a_prior_not_a_vehicle_count(monkeypatch):
    connection = FakeConnection(result=(3.0, 25))
    monkeypatch.setattr(traffic_sumo_prediction, "connect_to_warehouse", lambda: connection)

    period, rows = traffic_sumo_prediction._target_demand(1, "08:00")

    assert period == pytest.approx(2.94)
    assert rows == 25
    assert "avg(CASE los" in connection.calls[0][0]
