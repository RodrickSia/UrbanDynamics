# Plan display and Development simulation

The `feat/khoi-building-impact-simulation` branch is merged into the plan editor branch. Its planning studies, worker, native SUMO/SWMM, cancellation/retry and immutable results are used directly by Development.

## Display

- Existing and proposals show the current parcel palette throughout the saved study area. Plan MVTs now carry `mdsdd` and `color`; the URL schema changes to avoid old outline-only cached tiles.
- Saved zoning uses the selected zoning type color above current parcel colors. Draft zoning remains an orange outline.
- Baseline 3D display is clipped to the study area, preserving provider paint and height properties. Tile fragments with the same provider ID are unioned before clipping. Geometry without IDs is supported. Demolition masks suppress intersecting baseline footprints without editing their source.
- Vector tile properties are converted to plain objects before creating GeoJSON display sources. Their null-prototype form otherwise fails MapLibre worker serialization, leaving correctly clipped geometry invisible.
- Closing/deleting a plan restores the provider layers; changing scenario, basemap or 2D/3D refreshes the scoped display. The map uses actual polygon intersection because MapLibre's documented `within` filter evaluates points/lines, not building polygons: https://maplibre.org/maplibre-style-spec/expressions/#within.

## Simulation contract

`POST /api/v1/zoning/plans/{id}/simulation/studies` takes `revision`, `scenario_id` and editable density/surface/rainfall assumptions. It rejects stale plan revisions and freezes saved buildings and parcel snapshots into the existing planning study schema. It does not change the plan or use unsaved drawing state.

The UI then uses `/api/v1/planning/studies/{id}/runs`, polls `/jobs/{id}` and reads `/runs/{id}`. Screening estimates demand, runoff and geometric shade. Native runs SUMO and SWMM on explicitly synthetic infrastructure. Results and inputs stay server-side; local storage retains only settings and a job pointer bound to plan revision/scenario/settings. A changed revision hides old results. A failed poll is not interpreted as a cancelled job.

Each physical building keeps one footprint and height. `space_uses` groups its physical floor areas and occupancy by use for demand calculation. `gross_floor_area_m2` separately respects GFA exclusions, including zero. Excluded physical floors are not automatically treated as unoccupied. Commercial currently uses the simulation library's `other` coefficients, disclosed in Assumptions. Model versions advance to planning 0.19 and integrated 1.5; older stored results remain readable, but old studies require new revisions to run with the changed model.

Baseline building occupancy, actual ground surfaces, regional loads and network capacity are not verified by a parcel geometry snapshot. The adapter labels its baseline surface placeholder and uses unknown occupancy/capacity. The UI reports proposed demand, keeps change versus Existing and capacity unknown, and does not present placeholder differences as measured impacts. Real context/snapshot APIs from the merged branch remain available separately.

Engine bounds remain explicit: up to six developed parcels, twenty buildings per parcel, single Polygon sites/footprints, 100 floors/400 m per building. These limits do not reduce the editor's independent capabilities.

## Runtime

The main Compose stack now includes `planning-worker`, sharing the warehouse and solver volume with backend. Backend depends on worker startup, so the existing backend deployment command also starts it. No deployment is performed by these code changes.

For isolated local development, API and worker must use the same `PLANNING_SQLITE_PATH` and `SIMULATION_WORK_DIR`. Start the worker with `python -m app.services.simulation.planning.worker`. A queued job stays visible and cancellable when a worker is unavailable.

## Verification

Regression coverage includes mixed floor demand/geometry accounting, immutable input/revision conflicts, real screening/native engine execution, source clipping with holes/overlapping tiles/no IDs, scenario isolation, 2D/3D/style reload, restoration on exit, browser simulation polling/reload and responsive layouts. Warehouse-backed parcel MVT color checks require the isolated PostGIS test environment; fixture browser tiles alone do not establish live warehouse health.
