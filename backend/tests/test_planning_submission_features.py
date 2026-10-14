import copy
import math

import pytest
from shapely.geometry import shape

from app.services.simulation.integrated.background import publish
from app.services.simulation.planning import system_demo
from app.services.simulation.planning.context import build_context, canonical_input
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.vietnam_rules import apartment_density, catalog


def rectangle(x1, y1, x2, y2):
    return {"type": "Polygon", "coordinates": [[[x1,y1],[x2,y1],[x2,y2],[x1,y2],[x1,y1]]]}


@pytest.fixture
def installed(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SYSTEM_DEMO_ENABLED", "1")
    monkeypatch.setenv("PLANNING_SYSTEM_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("PLANNING_COUNTING_REFERENCE_DIR", str(tmp_path / "counting"))
    # Two source parcels share a full edge. Third is detached; fourth overlaps.
    geometries = [rectangle(106.758,10.820,106.759,10.821),rectangle(106.759,10.820,106.760,10.821),
                  rectangle(106.762,10.820,106.763,10.821),rectangle(106.7585,10.820,106.7595,10.821)]
    doc = {"schema_version": 1, "captured_at": "2026-10-14T00:00:00Z", "bbox": [106.75,10.81,106.77,10.83],
           "sources": {}, "parcels": {"features": [{"type":"Feature","id":i+1,"geometry":g,"properties":{"mdsdd":"ODT" if i==0 else "DGT","loai_dat_qh":"Nhà ở" if i==0 else "giao thông"}} for i,g in enumerate(geometries)]},
           "population": {"statistics":{"population_sum":2500}}, "layers": {},
           "osm": {"elements": [{"type":"way","id":1,"tags":{"building":"yes","building:levels":"2"},
                   "geometry":[{"lon":x,"lat":y} for x,y in rectangle(106.7588,10.8202,106.7592,10.8206)["coordinates"][0]]}]}}
    return publish(doc,tmp_path), doc


def study(identifier, **kw):
    return PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=identifier,parcel_ids=["1","2"],parcel_groups=[["1","2"]],
                       housing_units=20,residents=60,floors=4,floor_area_m2=1600,**kw)))


def test_union_is_one_plan_and_keeps_original_sources(installed):
    grouped = study(installed[0],background_mode="synthetic_capacity_v1",planning_catalog="qcvn_urban_2021")
    assert len(grouped.projects)==1
    assert grouped.system_parcel_groups=={"P1":["1","2"]}
    assert not grouped.system_parcel_bindings
    building=grouped.projects[0].development.buildings[0]
    assert building.units==20 and building.residents==60 and building.gross_floor_area_m2==1600
    members=[shape(f["geometry"]) for f in installed[1]["parcels"]["features"][:2]]
    assert shape(grouped.projects[0].site.model_dump()).equals(members[0].union(members[1]))
    assert len(grouped.projects[0].baseline.buildings)==1  # Straddling roof counted once.
    context=build_context(grouped)
    review=context["system_background"]["planning_review"][0]
    assert len(review["source_parcel_reviews"])==2
    assert review["flags"] and not review["legal_approval_established"]
    assert review["qcvn_density_check"]["maximum_percent"] is not None
    assert context["sha256"]==build_context(PlanningStudy(**canonical_input(grouped)))["sha256"]
    result=run_screening(grouped)
    assert result["options"][0]["state"]["vietnam_planning_requirements"]["catalog_sha256"]==catalog()["sha256"]
    # Baseline accounted once, replacement does not multiply 60 by two parcels.
    assert sum(b.residents for b in grouped.projects[0].development.buildings)==60


@pytest.mark.parametrize("ids,groups,match", [(["1","3"],[["1","3"]],"adjacent"),(["1","4"],[["1","4"]],"overlap"),
                                            (["1","2"],[["1"],["1","2"]],"disjoint"),(["1","2"],[["1"]],"exactly")])
def test_invalid_groups_rejected(installed,ids,groups,match):
    with pytest.raises(ValueError,match=match):
        system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=ids,parcel_groups=groups))


def test_supplied_group_building_cannot_extend_outside_site(installed):
    design=study(installed[0]).projects[0].development.model_dump(mode="json")
    design["buildings"][0]["footprint"]=rectangle(106.758,10.820,106.762,10.821)
    with pytest.raises(ValueError):
        study(installed[0],group_developments={"G1":design})


def test_source_geometry_cannot_be_replaced_in_persisted_group(installed):
    grouped=study(installed[0])
    grouped.system_parcel_groups["P1"]=["1","3"]
    with pytest.raises(ValueError,match="adjacent|geometry"):
        build_context(grouped)


def test_individual_mode_and_common_program_still_work(installed):
    result=PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=installed[0],parcel_ids=["1","2"],equal_program=True,floor_area_m2=1600)))
    assert len(result.projects)==2 and result.system_parcel_bindings=={"P1":"1","P2":"2"}


def test_qcvn_table_nodes_midpoints_and_boundaries():
    assert apartment_density(3000,16)==75
    assert apartment_density(10000,19)==60
    assert apartment_density(6500,19)==pytest.approx(67.5)
    assert apartment_density(6500,17.5)==pytest.approx(68.75)
    assert apartment_density(35000,47)==35
    assert apartment_density(1000,10)==75
    with pytest.raises(ValueError):
        apartment_density(0,16)


def test_qcvn_unknown_occupancy_not_converted_to_zero_and_levels_not_inferred(installed):
    result=run_screening(study(installed[0],planning_catalog="qcvn_urban_2021"))
    check=result["baseline"]["vietnam_planning_requirements"]
    assert check["water_domestic_minimum_m3_day"] is None
    assert all(row["required_places"] is None for row in check["school_provision"])
    assert all(row["status"]=="unknown_school_level_or_inventory" for row in check["school_radius_checks"])


def test_qcvn_is_separate_from_operational_coefficients_and_capacity(installed):
    without=study(installed[0],background_mode="synthetic_capacity_v1")
    with_catalog=study(installed[0],background_mode="synthetic_capacity_v1",planning_catalog="qcvn_urban_2021")
    old=run_screening(without);new=run_screening(with_catalog)
    assert old["options"][0]["state"]["metrics"]==new["options"][0]["state"]["metrics"]
    assert without.utility_zones==with_catalog.utility_zones
    check=new["options"][0]["state"]["vietnam_planning_requirements"]
    assert check["water_domestic_minimum_m3_day"]==pytest.approx(check["residents_basis"]*.08)
    assert {row["level"]:row["required_places"] for row in check["school_provision"]}=={
        "kindergarten":math.ceil(check["residents_basis"]*.05),"primary":math.ceil(check["residents_basis"]*.065),"lower_secondary":math.ceil(check["residents_basis"]*.055)}
    assert not check["legal_approval_established"]
