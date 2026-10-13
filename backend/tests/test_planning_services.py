from copy import deepcopy

import pytest

from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.services import allocate


def test_residual_reassignment_serves_restricted_group_instead_of_greedy_failure():
    groups = [{"id": "flexible", "students": 10}, {"id": "restricted", "students": 10}]
    facilities = [{"id": "near", "available_places": 10}, {"id": "far", "available_places": 10}]
    distances = {("flexible", "near"): 10, ("flexible", "far"): 20,
                 ("restricted", "near"): 15, ("restricted", "far"): 200}
    result = allocate(groups, facilities, distances, 100)
    assert sum(a["students"] for a in result) == 20
    assert {(a["group_id"], a["facility_id"]) for a in result} == {("flexible", "far"), ("restricted", "near")}
    assert allocate(groups[::-1], facilities[::-1], distances, 100) == result


def test_shared_school_places_background_once_and_new_school_benefit():
    result = run_screening(PlanningStudy(**demo_study("cumulative")))
    options = {o["id"]: o["state"] for o in result["options"]}
    assert result["baseline"]["metrics"]["school_demand_students"] == 216
    assert options["A_only"]["metrics"]["school_demand_students"] == 324
    assert options["ABC"]["metrics"]["school_demand_students"] == 405
    assert options["ABC"]["metrics"]["school_unserved_students"] < options["A_only"]["metrics"]["school_unserved_students"]
    for state in [result["baseline"]]+list(options.values()):
        service = state["school_services"]
        assert all(service["validity"].values())
        assert service["metrics"]["school_served_students"]+service["metrics"]["school_unserved_students"] == service["metrics"]["school_demand_students"]
        assert all(a["distance_m"] <= 1200 for a in service["assignments"])
    assert result["phases"][2]["state"]["school_services"] == options["ABC"]["school_services"]


def test_unknown_capacity_reports_access_without_inventing_unserved_zero():
    payload = demo_study()
    payload["school_facilities"][0]["capacity_places"] = None
    result = run_screening(PlanningStudy(**payload))
    service = result["baseline"]["school_services"]
    assert service["comparability"] == "insufficient_data"
    assert service["metrics"]["school_unserved_students"] is None
    assert service["groups"][0]["nearest_school_distance_m"] is not None
    assert all(i["metrics"]["school_unserved_students"] is None for i in result["interaction_effects"])


def test_missing_background_demand_and_healthcare_not_school_places():
    payload = demo_study("cumulative")
    payload["background_school_groups"] = []
    payload["projects"][1]["development"]["buildings"][0]["use"] = "hospital"
    state = next(o["state"] for o in run_screening(PlanningStudy(**payload))["options"] if o["id"] == "ABC")
    assert state["school_services"]["background_demand_missing"]
    assert all(f["id"] != "project_B" for f in state["school_services"]["facilities"])
    assert state["metrics"]["school_unserved_students"] is None


def test_service_geometry_and_capacity_validation():
    payload = demo_study()
    payload["school_facilities"][0]["reserved_places"] = 300
    with pytest.raises(ValueError, match="Reserved school"):
        PlanningStudy(**payload)
    payload = demo_study()
    payload["background_school_groups"][0]["location"] = [0, 0]
    with pytest.raises(ValueError, match="outside the study"):
        PlanningStudy(**payload)


def test_default_zero_school_design_capacity_is_unknown():
    payload = demo_study("cumulative")
    payload["projects"][1]["development"]["buildings"][0]["service_capacity"] = 0
    state = next(o["state"] for o in run_screening(PlanningStudy(**payload))["options"] if o["id"] == "ABC")
    assert "project_B" in state["school_services"]["unknown_capacity_facility_ids"]
    assert state["metrics"]["school_unserved_students"] is None


def test_osm_foot_paths_restrictions_detour_and_disconnected_no_fallback():
    from app.services.simulation.integrated.road_network import walking_graph, walking_route
    def way(i, nodes, coords, **tags):
        return {"type": "way", "id": i, "nodes": nodes,
                "geometry": [{"lon": x, "lat": y} for x,y in coords],
                "tags": {"highway": "residential", **tags}}
    forward = lambda x,y: (x,y)
    doc = {"elements": [way(1,[1,2,3,4],[(0,0),(0,100),(100,100),(100,0)],oneway="yes"),
                        way(2,[1,4],[(0,0),(100,0)],foot="no"),
                        way(3,[5,6],[(1000,0),(1100,0)])]}
    graph = walking_graph(doc, forward)
    route = walking_route(graph,(0,0),(100,0),forward)
    assert route["distance_m"] == 300
    assert route["node_ids"] == [1,2,3,4]
    assert walking_route(graph,(100,0),(0,0),forward)["distance_m"] == 300
    assert walking_route(graph,(0,0),(1000,0),forward) is None
    assert walking_route(graph,(0,0),(2000,0),forward) is None
    restricted = {"elements": [way(1,[1,2],[(0,0),(100,0)],**{"oneway:foot":"yes"})]}
    assert walking_route(walking_graph(restricted,forward),(100,0),(0,0),forward) is None
    assert walking_route(walking_graph(restricted,forward),(0,0),(100,0),forward)
