from copy import deepcopy

import pytest

from app.services.simulation.planning.drainage import combine_runoff
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.native import run_native
from app.services.simulation.planning.presets import demo_study


def hydrograph(identifier, values, minute=None):
    return {"catchment_id": identifier, "timeseries": {"sample_interval_seconds": 60,
            "minute": minute or list(range(1, len(values)+1)), "runoff_m3_s": values}}


def test_different_and_coincident_peaks_are_aggregated_at_matching_times():
    first = hydrograph("A", [1, 5, 1, 0])
    later = hydrograph("B", [0, 1, 5, 1])
    result = combine_runoff([first, later])
    assert result["runoff_m3_s"] == [1, 6, 6, 1]
    assert result["peak_m3_s"] == 6 < 10
    assert result["peak_minute"] == 2
    assert combine_runoff([later, first]) == result
    coincident = combine_runoff([first, hydrograph("B", [1, 5, 1, 0])])
    assert coincident["peak_m3_s"] == 10
    assert combine_runoff([hydrograph("empty", [0, 0])])["peak_minute"] is None


@pytest.mark.parametrize("mutation", ["shift", "different_step", "wrong_length", "negative", "nan", "unordered", "duplicate"])
def test_incompatible_or_invalid_hydrographs_are_rejected(mutation):
    first = hydrograph("A", [1, 5, 1])
    second = hydrograph("B", [0, 1, 5])
    if mutation == "shift":
        second["timeseries"]["minute"] = [2, 3, 4]
    elif mutation == "different_step":
        second["timeseries"].update(sample_interval_seconds=120, minute=[2, 4, 6])
    elif mutation == "wrong_length":
        second["timeseries"]["runoff_m3_s"].pop()
    elif mutation == "negative":
        second["timeseries"]["runoff_m3_s"][0] = -1
    elif mutation == "nan":
        second["timeseries"]["runoff_m3_s"][0] = float("nan")
    elif mutation == "unordered":
        second["timeseries"]["minute"] = [1, 3, 2]
    else:
        second["catchment_id"] = "A"
    with pytest.raises(ValueError):
        combine_runoff([first, second])


def test_native_swmm_catchment_profiles_and_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    payload = demo_study("cumulative")
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    payload["catchments"] = [{"id": "urban", "source": "Synthetic paved catchment",
                              "background_area_m2": 20000, "background_impervious_percent": 100},
                             {"id": "green", "source": "Synthetic vegetated catchment",
                              "background_area_m2": 80000, "background_impervious_percent": 0}]
    for project in payload["projects"]:
        project["catchment_id"] = "urban" if project["id"] == "A" else "green"
    study = PlanningStudy(**payload)
    result = run_native(study)
    state = next(o["state"] for o in result["options"] if o["id"] == "ABC")
    by_id = {c["catchment_id"]: c for c in state["drainage"]["catchments"]}
    children = [by_id[c.id] for c in study.catchments]
    assert all(c["balance_passed"] for c in children)
    expected = [{"J_A"}, {"J_B", "J_C"}]
    for child, project_nodes in zip(children, expected):
        reported = {n["id"] for n in child["nodes"]}
        assert reported >= project_nodes | {"J0", "O0"}
        assert reported.isdisjoint(({"J_A", "J_B", "J_C"} - project_nodes))
    combined = combine_runoff(children)
    assert state["drainage"]["combined_runoff_m3_s"] == combined["runoff_m3_s"]
    assert state["drainage"]["combined_runoff_time_minutes"] == combined["minute"]
    assert state["metrics"]["runoff_peak_m3_s"] == combined["peak_m3_s"]
    first, second = [c["timeseries"]["runoff_m3_s"] for c in children]
    assert combined["runoff_m3_s"] == pytest.approx([a+b for a, b in zip(first, second)])
    assert combined["peak_m3_s"] <= max(first)+max(second)+1e-8
    # Actual SWMM profiles have different shapes; intentional time alignment is
    # validated separately with a known staggered/coincident peak fixture.
    assert first != second
    broken = deepcopy(payload)
    broken["projects"][0]["catchment_id"] = "missing"
    with pytest.raises(ValueError, match="Unknown catchment"):
        PlanningStudy(**broken)
