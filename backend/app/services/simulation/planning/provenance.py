"""Frozen synthetic-source manifest with explicit per-module spatial limits."""
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

from ..integrated.context import digest, projection
from .network import specification


def build(study, inputs, library, model_version, background=None):
    from .context import canonical_numbers
    region = shape(inputs["study_area"])
    spec = specification(study)
    sources = []

    def source(identifier, payload, note, coverage, declared_kind=None, version=None):
        sources.append({"id": identifier, "source_kind": "synthetic",
                        "declared_source_kind": declared_kind,
                        "version": version or model_version,
                        "payload_sha256": digest(canonical_numbers(payload)),
                        "note": note, "coverage": coverage,
                        "observed_at": None, "time_basis": "Declared scenario input, not an observed timestamp"})

    source("parcel_geometry", [{"id": p["id"], "site": p["site"]} for p in inputs["projects"]],
           "User-selected hypothetical parcels; duplicate physical geometry evaluated once", "registered_parcels")
    source("baseline_inventory", [{k: p[k] for k in ("id", "site", "baseline", "baseline_source", "baseline_kind", "baseline_occupancy")} for p in inputs["projects"]],
           "Declared existing designs and occupancy, not an inferred empty site", "registered_parcels")
    sources[-1]["declared_source_kinds"] = {p["id"]: p["baseline_kind"] for p in inputs["projects"]}
    source("development_programs", [{"id": p["id"], "development": p["development"]} for p in inputs["projects"]],
           "Complete final parcel state; retained buildings must be included", "registered_parcels")
    source("demand_coefficients", library, "Versioned coefficient library; assumptions are not locally calibrated", "declared_program_types", version=library["version"])
    source("regional_population", {"residents": inputs["background_residents"], "transfers": inputs["resident_transfers"]},
           "Background excludes registered parcels; transfers are already included in final counts", "nonspatial_population_total")
    traffic_geometry = unary_union([shape(f["geometry"]) for f in spec["map"]["features"]]).envelope
    source("traffic_network", spec, "Generated common corridor, private accesses and signal method; exact specification supplied to netconvert", mapping(traffic_geometry))
    source("traffic_background", {"vehicles_hour": inputs["background_vehicles_hour"], "traffic_hours": inputs["conditions"]["traffic_hours"], "motorcycle_fraction": .75},
           "Synthetic external through traffic; no camera calibration or regional OD measurement", "shared_corridor_external_boundaries")
    if study.traffic_prior:
        sources[-1].update(source_kind=study.traffic_prior.source_kind,
            payload_sha256=digest(inputs['traffic_prior']),note=study.traffic_prior.source)
    source("rain_event", {k: inputs["conditions"][k] for k in ("rainfall_mm", "rainfall_duration_minutes")},
           "Uniform hypothetical rain event and 180-minute recession, not an IDF return period", "all_declared_catchments")
    source("drainage_graph", {"catchments": inputs["catchments"], "bindings": [{"id": p["id"], "site": p["site"], "catchment_id": p["catchment_id"]} for p in inputs["projects"]], "soil_and_conduit_library": library["swmm"], "manning_n": library["drain_manning_n"]},
           "Generated shared branches/trunk/free outfall; outside-parcel catchment area is scalar without a surveyed boundary", "declared_graph_and_nonspatial_background_area")
    source("utility_zones", inputs["utility_zones"], "Shared capacity/background profiles by zone ID; no electrical/hydraulic network or mapped service-area boundary", "zone_bindings_only")
    sources[-1]["declared_source_kinds"] = {z["id"]: z["source_kind"] for z in inputs["utility_zones"]}
    source("school_inventory", {"facilities": inputs["school_facilities"], "groups": inputs["background_school_groups"], "school_age_fraction": inputs["school_age_fraction"]},
           "Declared capacity/reserved places and student groups; not verified enrollment or eligibility", "declared_locations_and_capacity")
    source("walking_network", {"sites": [p["site"] for p in inputs["projects"]], "spine_offset_m": 150, "max_walk_m": inputs["school_max_walk_m"], "speed_m_s": inputs["school_walk_speed_m_s"]},
           "Synthetic perpendicular connectors and common walking spine; no surveyed sidewalks/crossings", "generated_school_routes")
    source("solar_geometry", {"date": inputs["conditions"]["solar_date"], "hours": list(range(8,18)), "area": inputs["study_area"], "fixed_receiver_policy": "Exclude union of every possible building footprint"},
           "Fixed flat outdoor receiver, opaque buildings/trees; no neighbour buildings beyond declared inventory", mapping(region))
    if inputs["background_snapshot"]:
        source("inclusive_background_snapshot", inputs["background_snapshot"], "Explicit parcel contribution subtraction before any scenario; no inferred missing contributions", inputs["background_snapshot"]["coverage"], declared_kind=inputs["background_snapshot"]["source_kind"])

    forward, backward = projection(region)
    projected_sites = [transform(forward, shape(p.site.model_dump())) for p in study.projects]
    spine_y = max(p.centroid.y for p in projected_sites)+150
    points = [p.centroid for p in projected_sites]+[transform(forward, Point(f.location)) for f in study.school_facilities]+[transform(forward, Point(g.location)) for g in study.background_school_groups]
    # Bound the actual published WGS84 route vertices. Inverse-projecting a
    # local rectangle's corners can clip interior points along its curved edge.
    walk_geometry = unary_union([shape(p.site.model_dump()) for p in study.projects]+
                                [transform(backward, p) for p in points+[Point(p.x, spine_y) for p in points]]).envelope
    module_sources = {
        "geometry": ["parcel_geometry", "baseline_inventory", "development_programs"],
        "traffic": ["traffic_network", "traffic_background", "baseline_inventory", "development_programs", "demand_coefficients"],
        "drainage": ["drainage_graph", "rain_event", "baseline_inventory", "development_programs", "demand_coefficients"],
        "utilities": ["utility_zones", "baseline_inventory", "development_programs", "demand_coefficients"],
        "school": ["school_inventory", "walking_network", "regional_population", "baseline_inventory", "development_programs"],
        "shadow": ["solar_geometry", "baseline_inventory", "development_programs"]}
    modules = {name: {"source_ids": ids, "status": "synthetic_scenario_only", "observed_coverage": False} for name, ids in module_sources.items()}
    if inputs["background_snapshot"]:
        for module in ("utilities", "traffic", "drainage", "school"):
            if module in inputs["background_snapshot"]["included_modules"]:
                modules[module]["source_ids"] = modules[module]["source_ids"]+["inclusive_background_snapshot"]
        if "population" in inputs["background_snapshot"]["included_modules"]:
            modules["geometry"]["source_ids"] = modules["geometry"]["source_ids"]+["inclusive_background_snapshot"]
    modules["geometry"].update(required_scope="registered_parcels", geometry=mapping(unary_union([shape(p["site"]) for p in inputs["projects"]])))
    modules["traffic"].update(required_scope="whole_generated_corridor_and_external_boundaries", geometry=mapping(traffic_geometry),
                              inside_study_area=region.covers(traffic_geometry), edge_count=len(spec["edges"]),
                              boundary_policy="All trips terminate at declared west/east boundaries or parcel accesses; no outside-city routing")
    modules["school"].update(required_scope="all_declared_facilities_groups_and_generated_paths", geometry=mapping(walk_geometry),
                             missing_background_demand=bool(background["residents"] and not background["school_groups"]) if background is not None else bool(study.background_residents and not study.background_school_groups),
                             potential_unknown_design_capacity_ids=sorted(p.id for p in study.projects if any(b.use == "school" and b.service_capacity == 0 for d in (p.baseline, p.development) for b in d.buildings)),
                             unknown_capacity_ids=sorted(f.id for f in study.school_facilities if f.capacity_places is None))
    modules["drainage"].update(required_scope="all_declared_graphs_and_bound_scalar_background_areas",
                               catchment_ids=sorted(c.id for c in study.catchments),
                               background_area_has_surveyed_polygon=False,
                               terrain_2d_coverage=False, boundary_policy="Synthetic free outfall, no tide/backwater boundary data")
    modules["utilities"].update(required_scope="shared_zone_ids_and_background_profiles", zone_ids=sorted(z.id for z in study.utility_zones),
                                unknown_capacities=[{"zone_id": z.id, "capacity": key} for z in sorted(study.utility_zones, key=lambda z: z.id) for key in ("power_capacity_kw", "water_capacity_m3_day", "wastewater_capacity_m3_day") if getattr(z, key) is None or z.source_kind == "unknown"],
                                service_boundary_polygons_available=False, network_flow_available=False)
    modules["shadow"].update(required_scope="fixed_study_outdoor_receivers", geometry=inputs["study_area"],
                             neighbouring_inventory_beyond_declared_parcels=False)
    if study.data_mode == "demo_system":
        from .system_demo import load
        snapshot = load(study.system_snapshot_id)
        from ..integrated.road_network import walking_graph
        from shapely.geometry import LineString
        topology = walking_graph(snapshot.get("osm", {}), forward)
        walk_geometry = unary_union([LineString(s) for s in topology["segments"]]+[
            transform(backward, p) for p in points]).envelope
        modules["school"].update(required_scope="installed_osm_foot_graph_and_estimated_endpoint_connectors",
            geometry=mapping(walk_geometry), walking_network_kind="osm_with_estimated_connectors",
            maximum_endpoint_connector_m=300, fallback_to_synthetic_spine=False)
        from .spatial import fixed_context
        fixed = fixed_context(study)
        sources.append({"id": "fixed_solar_context", "source_kind": "mixed_sourced_inputs",
            "version": study.system_snapshot_id, "payload_sha256": digest(canonical_numbers(fixed)),
            "observed_at": None, "coverage": "OSM extract within 300 m of registered parcel union, excluding on-site objects",
            "note": "Clipped off-site footprints, OSM heights/floors/crowns where tagged; missing attributes have explicit defaults. Incomplete inventory, flat receivers and opaque trees, not a thermal model."})
        modules["shadow"]["source_ids"].append("fixed_solar_context")
        modules["shadow"].update(neighbouring_inventory_beyond_declared_parcels=bool(fixed["features"]),
            context_inventory_complete=False, fixed_context_object_count=len(fixed["features"]),
            maximum_context_distance_m=300)
        for entry in sources:
            if entry["id"] == "parcel_geometry":
                entry.update(source_kind="team_sourced_geometry", version=study.system_snapshot_id,
                             note="Exact installed system parcel geometry; one-part MultiPolygon normalization preserves geometry. Not a legal applicability certificate.")
            elif entry["id"] == "baseline_inventory":
                entry.update(source_kind="mixed_sourced_inputs",
                             note="OSM-clipped footprints and historical WorldCover classification where installed, with assumed unmapped surfaces; no surveyed occupancy or complete inventory.")
            elif entry["id"] == "walking_network":
                entry.update(source_kind="mixed_sourced_inputs", version=study.system_snapshot_id,
                    payload_sha256=digest(canonical_numbers({"osm": snapshot.get("osm", {}),
                        "maximum_connector_m": 300, "max_walk_m": study.school_max_walk_m,
                        "speed_m_s": study.school_walk_speed_m_s})), coverage=mapping(walk_geometry),
                    note="OSM foot topology, explicit foot restrictions and shortest paths; endpoint connectors are estimated straight segments, not verified entrances/sidewalks. No generated-spine fallback.")
            elif entry["id"] == "regional_population":
                entry.update(source_kind="estimated", version=study.system_snapshot_id,
                             note="Inclusive WorldPop bbox prior; unknown selected-parcel occupancy prevents exact subtraction. Not a census or an established population change.")
                if study.background_snapshot and study.background_snapshot.id == "synthetic_capacity_v1":
                    entry.update(source_kind="synthetic", version="synthetic_capacity_v1", note=study.background_snapshot.source)
            elif entry["id"] in ("traffic_background", "utility_zones"):
                if entry['id']!='traffic_background' or study.traffic_prior is None:
                    entry.update(source_kind="unknown", note="No verified traffic background or utility capacity. Numerical scenario placeholders do not establish observed loads.")
                if entry["id"] == "utility_zones" and study.background_snapshot and study.background_snapshot.id == "synthetic_capacity_v1":
                    entry.update(source_kind="synthetic", note="Fixed fictional external utility loads and capacities; no surveyed service network")
            elif entry["id"] == "traffic_network" and study.traffic_network_mode == "osm_snapshot":
                entry.update(source_kind="mixed_sourced_inputs",version=study.system_snapshot_id,
                             note="Public road topology imported from installed OSM extract. Private accesses, phase timings and OD prior are hypothetical. Frozen coverage counts source ways; actual directed edge geometry is exported with native artifacts.")
        sources.append({"id": "system_snapshot", "source_kind": "mixed_sourced_inputs",
                        "version": study.system_snapshot_id, "payload_sha256": study.system_snapshot_id,
                        "observed_at": None, "captured_at": snapshot["captured_at"],
                        "time_basis": "Snapshot capture time; observation dates remain in original source metadata",
                        "coverage": snapshot["bbox"], "note": "Actual system parcels, WorldPop estimate, OSM/context layers; no measured OD, sewer, occupancy or capacity"})
        for module in modules.values():
            module["source_ids"] = module["source_ids"]+["system_snapshot"]
            module["status"] = "mixed_demo_not_calibrated"
        if snapshot.get("landcover"):
            sources.append({"id": "historical_landcover", "source_kind": "historical_classification",
                "version": "ESA WorldCover 2021 v200", "payload_sha256": digest(snapshot["landcover"]),
                "observed_at": None, "time_basis": "2021 annual classification, not a current survey",
                "coverage": snapshot["bbox"], "metadata": snapshot["landcover"]["metadata"],
                "note": "10 m classification supplies green/built-up surface proxies after known roofs are removed; built-up is not a measured impervious fraction or a building footprint."})
            for module in ("geometry", "drainage"):
                modules[module]["source_ids"].append("historical_landcover")
        if study.traffic_prior and study.traffic_prior.counting_reference_id:
            from .counting_reference import load as load_counting
            counting=load_counting(study.traffic_prior.counting_reference_id)
            sources.append({'id':'counting_reference','source_kind':'model_count_estimate',
                'version':study.traffic_prior.counting_reference_id,'payload_sha256':study.traffic_prior.counting_reference_id,
                'observed_at':None,'coverage':'Unmapped historical UIT-ADrone line; not this parcel network',
                'note':'Repaired model counts without independent complete crossing labels. Vehicle mix only; amplitude/OD/day shape are scenario assumptions.',
                'video_sha256':counting['source_sha256'],'tracks_sha256':counting['tracks_sha256']})
            modules['traffic']['source_ids'].append('counting_reference')
    limitations = [
        "Generated traffic/drainage/walking graphs are not surveyed infrastructure; source coverage is not model calibration.",
        "WorldPop is an inclusive bbox prior; unknown parcel occupancy prevents exact deduplication and established baseline changes.",
        "Traffic loads and utility capacities are unverified; missing values are not observations."] if study.data_mode == "demo_system" else [
        "Synthetic coverage is complete only for the declared generated model; it does not establish observed data coverage.",
        "Background population, utility loads, OD and school groups exclude registered parcels; regional aggregates need explicit deduplication before ingestion.",
        "No observation timestamps are fabricated; declared source kinds do not override this study's synthetic mode."]
    if study.background_snapshot and study.background_snapshot.id == "synthetic_capacity_v1":
        limitations[1] = "Explicit synthetic capacity v1 replaces population demand; WorldPop is context only. Occupancy assumptions are hashed and subtracted; this is not a surveyed baseline."
    manifest = canonical_numbers({"version": model_version, "source_kind": "mixed_demo" if study.data_mode == "demo_system" else "synthetic", "entries": sources,
                                  "coverage": {"modules": modules}, "limitations": limitations})
    manifest["sha256"] = digest(manifest)
    manifest["id"] = "planning-sources-"+manifest["sha256"]
    return manifest
