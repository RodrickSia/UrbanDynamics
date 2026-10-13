import pytest
from count_core import Line, aggregate


def test_finite_line_direction_deadband_and_no_repeat():
    line = Line("gate", (0, 10), (100, 10), "in", "out", margin=2)
    assert line.update(1, (20, 3), 0, 10) is None
    assert line.update(1, (20, 9), 1, 10) is None
    event = line.update(1, (20, 17), 2, 10)
    assert event["direction"] == "in" and event["frame"] == pytest.approx(1)
    assert line.update(1, (20, 3), 3, 10)["direction"] == "out"
    assert line.update(1, (20, 17), 4, 10) is None
    assert line.update(2, (120, 3), 0, 10) is None
    assert line.update(2, (120, 17), 2, 10) is None


def test_disappearance_cannot_invent_crossing_and_ids_are_separate():
    line = Line("gate", (0, 10), (100, 10), margin=1)
    line.update(1, (20, 0), 0, 10)
    assert line.update(1, (20, 20), 20, 10) is None
    line.update(2, (20, 0), 21, 10)
    assert line.update(2, (20, 20), 22, 10)["track_id"] == 2
    line.prune(50, 10)
    assert not line.states


def test_bins_conserve_counts_and_last_bin_has_actual_duration():
    events = [{"line_id": "g", "direction": "in", "vehicle_class": "motorcycle", "video_seconds": second}
              for second in (2, 60, 79)]
    rows = aggregate(events, 0, 80, 60)
    assert sum(r["count"] for r in rows) == 3
    assert rows[0]["count"] == 1 and rows[1]["observed_seconds"] == 20
    assert rows[1]["extrapolated_vehicles_hour"] == 360


def test_invalid_geometry_and_observation_rejected():
    with pytest.raises(ValueError):
        Line("g", (0, 0), (0, 0))
    with pytest.raises(ValueError):
        aggregate([], 0, 0, 60)
