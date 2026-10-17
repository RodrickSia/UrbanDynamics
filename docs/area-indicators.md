# Selected-area indicators

## Research and scope

Esri distinguishes [overview indicators](https://doc.esri.com/en/arcgis-urban/latest/help/help-custom-indicators.html) (external scenes/dashboards) from [plan metrics](https://doc.esri.com/en/arcgis-urban/latest/help/help-metrics-plan.html) calculated from spaces, surfaces and existing values. Its dashboard supports scenario switching and parcel selections. UrbanDynamics combines selected-area analysis with the existing plan editor, without requiring ArcGIS services.

Implement: draw an analysis polygon without creating a plan, or use the open plan's study area; show population, current land-use shares, energy/water/waste estimates, transit proximity, housing capacity and employment. A scenario toggle controls both map proposals and calculations. Keep current plan validation/comparison available in a collapsed section.

## Calculation contract

- AOI is a valid polygon in the HCMC pilot, 10 m²–25 km², at most 2,000 vertices. All quantities are clipped to this polygon, not its bounding box.
- WorldPop population uses the latest loaded year, with per-cell population weighted by intersected cell area. Coverage and year accompany the result; missing raster is unknown, never zero.
- Parcel shares use disjoint unions of current parcel geometry. Conflicting overlaps and unmapped space remain explicit; percentages use the entire AOI as denominator. Proposed zoning distribution is separate from current cadastral use.
- Source reads have 10-second SQL timeouts and a 20,000-parcel limit. Larger selections return unavailable parcel statistics instead of misleading truncated percentages.
- Saved building floor uses contribute net usable floor area, estimated residents, dwelling units and jobs. Proposed contributions are shown separately from baseline values. Existing jobs/housing capacity cannot be inferred from parcel area. No baseline-plus-proposal total is claimed where existing occupancy/demolition is unknown.
- Residential energy, water, waste and labour demand are population × editable assumptions. Proposed nonresidential loads use floor area/jobs and separate coefficients. Defaults are illustrative assumptions, not measured Vietnamese demand or legal standards. Floor area exclusions affect capacity; they do not automatically eliminate physical demand.
- Commercial/office floors supply workplace estimates. `Other` uses have no calibrated rate; their presence makes the corresponding aggregate jobs/loads unknown rather than silently treating them as offices.
- Transit is area covered by a union of stop buffers, including stops outside the AOI. This is straight-line proximity, not network walking accessibility or service frequency. [UN SDG 11.2.1](https://unstats.un.org/sdgs/metadata/files/Metadata-11-02-01.pdf) instead requires network walking distances (500 m low-capacity / 1 km high-capacity). Show source date/coverage and do not label our proxy as the SDG measure.
- Requests include plan revision; stale revisions fail with 409. Calculations are read-only and do not save plans. Browser requests are abortable and keyed by AOI/scenario/revision/assumptions; old results cannot replace new ones.

## Delivery checks

Verify boundary clipping, holes, overlap percentages, zero vs missing data, scenario on/off, mixed floor uses, transit union/external stops, stale requests, invalid geometry, real browser drawing and responsive layout. No deployment.

## Running and data

`POST /api/v1/indicators/area` takes GeoJSON `geometry`, optional `plan_id`/`revision`/`scenario_id`, `include_scenario`, and editable `assumptions`. It returns baseline/proposal metrics separately, current land-use percentages, proposed zoning percentages, source coverage, and method notes. Plan writes and simulation runs are not needed.

Population and cadastral shares use the existing PostGIS warehouse. Missing sources stay null; an empty parcel query is represented as unmapped land. Population totals require at least 99% cell coverage and never extrapolate uncovered cells. Existing housing capacity now uses the generated residential building snapshot: intersected footprint × floors × net-area factor ÷ m²/home. It is modeled capacity, not occupied households, and source coverage remains unknown. Missing buildings or floors keep this estimate null. Existing job capacity/balance remain unknown because the connected inventory has no commercial/office floor-use data.

`area-indicators-2` adds `existing_buildings` provenance. The frontend supports older responses and explains when the backend does not yet provide building capacity. The same selected-area calculation serves Indicators and the plan Dashboard.

On 2026-10-17 the live `Hello` plan returned the reported 394.8 Existing / 259.6 Proposed population through `area-indicators-1`, with all three Existing capacity fields null. Its Development endpoint returned generated residential buildings (three buildings and 1,989.43 m² GFA in one saved zone), confirming that residential data existed but was not connected to Indicators. This zone sample is not the whole plan inventory.

Transit requires a local GeoJSON snapshot. Prepare it with the existing Python environment:

```powershell
python scripts/fetch-indicator-transit.py
```

The script queries public OpenStreetMap Overpass for bus stops and rail stations in the HCMC pilot bounds; it rejects incomplete responses and replaces the snapshot atomically. The optional `--endpoint https://overpass.private.coffee/api/interpreter` selects the mirror. Attribution, query bounds, capture date and source timestamp are preserved. Run explicitly to refresh; map requests never call Overpass. Compose already mounts `etl/data` at `/data`; native development can set `DATA_DIR=etl/data` or `INDICATORS_TRANSIT_PATH` to the file. The generated snapshot stays outside Git. A loaded OSM snapshot is still a proximity proxy, not a verified complete transport inventory.

Both Overpass endpoints returned HTTP 504 during implementation (2026-10-14), so no production stop snapshot was published. The unavailable state is intentional until a successful fetch or an operator-supplied snapshot exists.

## Verification

- Backend calculation/API tests cover clipping, overlap, partial/missing/zero data, mixed/unknown floor uses, transit boundaries and revision conflicts.
- The PostGIS raster regression is opt-in with `POSTGIS_TESTS=1` against an isolated migrated database; it rolls fixture writes back. No isolated PostGIS instance was available locally.
- Browser test uses the real app/API and deterministic source fixtures: draw without a plan, select a plan, toggle scenario, edit assumptions, switch Existing/proposal, recover from HTTP failure, close workspace, and inspect 320/768/1024/1440 px layouts.
- Browser setup: run `uvicorn indicators_testserver:app --host 127.0.0.1 --port 8087` with `PYTHONPATH=backend;etl;backend/tests` and an isolated `ZONING_DATA_DIR`, then `npx playwright test --config playwright.indicators.config.ts` in `frontend`.
