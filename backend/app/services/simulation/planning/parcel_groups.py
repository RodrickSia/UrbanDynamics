"""Union canonical source polygons once; do not union clipped vector tiles."""
from copy import deepcopy

from shapely.geometry import mapping, shape
from shapely.ops import unary_union, transform

from ..integrated.context import projection


def union_members(features):
    if not features:
        raise ValueError("A project requires at least one parcel")
    polygons = [shape(f["geometry"]) for f in features]
    forward, _ = projection(polygons[0])
    for i, polygon in enumerate(polygons):
        if polygon.geom_type != "Polygon" or not polygon.is_valid:
            raise ValueError("Group members must be complete valid single-part parcels")
        for other in polygons[:i]:
            if transform(forward, polygon.intersection(other)).area > .01:
                raise ValueError("Group parcels overlap; canonical source data must be reviewed")
    merged = unary_union(polygons)
    if merged.geom_type != "Polygon" or not merged.is_valid:
        raise ValueError("Select adjacent parcels sharing edges; detached or point-touching parcels cannot be one building site")
    return mapping(merged)


def prepare_grouped(body, document):
    from . import system_demo
    from .models import PlanningStudy
    available = {str(f["id"]): f for f in system_demo.candidates(document)}
    groups = body.parcel_groups
    flat = [identifier for group in groups for identifier in group]
    if any(not group or len(group) != len(set(group)) for group in groups) or len(flat) != len(set(flat)):
        raise ValueError("Choose nonempty disjoint parcel groups; a parcel cannot be used by two projects")
    if set(flat) != set(body.parcel_ids) or not set(flat) <= available.keys():
        raise ValueError("Groups must cover exactly the selected eligible source parcels")
    if body.developments or body.programs or body.scenario_parcels:
        raise ValueError("Grouped mode uses group_developments and the shared building program; per-parcel plans/scenarios cannot be multiplied into a group")
    if not set(body.group_developments) <= {"G"+str(i+1) for i in range(len(groups))}:
        raise ValueError("Group building plan requires a valid G1..Gn key")
    virtual = deepcopy(document)
    virtual["parcels"] = {"features": []}
    bindings = {}
    for i, group in enumerate(groups):
        gid = "G"+str(i+1)
        members = [available[key] for key in sorted(group)]
        geometry = union_members(members)
        virtual["parcels"]["features"].append({"type": "Feature", "id": gid, "geometry": geometry,
                                                "properties": {"source_parcel_ids": sorted(group)}})
        bindings["P"+str(i+1)] = sorted(group)
    # The normal builder clips baseline once against the union; no per-parcel
    # double counting of a building that straddles a shared boundary.
    request = body.model_copy(update={"parcel_ids": ["G"+str(i+1) for i in range(len(groups))],
                                     "parcel_groups": [], "group_developments": {},
                                     "developments": body.group_developments})
    result = system_demo.prepare(request, _document=virtual)
    result["system_parcel_bindings"] = {}
    result["system_parcel_groups"] = bindings
    for project in result["projects"]:
        project["title"] = "One project on parcels " + ", ".join(bindings[project["id"]])
    for option in result["options"]:
        if len(option["active_project_ids"]) == 1:
            option["title"] = "Build one project on " + ", ".join(bindings[option["active_project_ids"][0]])
    return PlanningStudy(**result).model_dump(mode="json")


def bindings(study):
    return study.system_parcel_groups or {key: [value] for key, value in study.system_parcel_bindings.items()}
