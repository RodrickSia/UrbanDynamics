# Frontend ↔ Backend Handoff

This is the current integration guide for the map frontend and FastAPI backend.
It describes what runs today, how to start the local stack, and what remains
for the frontend to consume the published datasets.

## Current status

- Compose runs `frontend`, `backend`, and PostGIS. The frontend is the only
  service published to the host (`http://localhost:8080` by default). Nginx
  forwards `/api/*`, `/health`, and `/ready` to the backend over the Compose
  network.
- The backend serves population rasters, flood history, satellite flood
  classifications, rainfall-threshold flood-risk indicators, and reviewed
  land-price segments from PostGIS.
- **The React map UI now consumes these datasets.** Data layers discovers
  backend availability, adds population PNG and flood/land-price MVT sources,
  and exposes year/palette, opacity, flood date filters, legends and inspection.
  All backend overlays are off until the user enables them. Existing measurement,
  Viewshed, POI and basemap controls remain separate.
- The current local database has WorldPop 2015–2030 (794 raster tiles per
  year), 131 flood-history observations, 131 flood-risk features, and 17
  satellite-classified features. Land-price rows have been extracted locally,
  but the published layer is empty until road geometries and values are
  reviewed.

## Start the local stack

From the repository root:

```sh
cp .env.example .env
```

Set a local `WAREHOUSE_PASSWORD` in `.env`. Set `VITE_GOONG_MAPTILES_KEY` if
you want the live Goong basemap; it is a browser-visible map-tile key. Then:

```sh
docker compose up -d --build postgis backend frontend
docker compose ps
```

Open the map at `http://localhost:8080`. API docs are at
`http://localhost:8080/api/v1/docs`; API discovery is at
`http://localhost:8080/api/v1`. Without a Goong map-tile key, the API remains
available but the map canvas displays its missing-key fallback.

The PostGIS data persists in the `postgis_data` Compose volume. Use
`docker compose down` to stop the stack while preserving that volume. Do not
publish backend or PostGIS ports to the host; frontend requests use the
same-origin `/api` proxy.

## Load local ETL data

Run the complete WorldPop pipeline:

```sh
docker compose --profile etl-population-hcmc run --rm \
  etl-population-hcmc run --stage all
```

The API needs the warehouse migrations before ETL publishes vector layers.
Fresh PostGIS databases apply them during initialization. For an existing
database, follow [warehouse operations](../infra/warehouse/README.md). Pipeline
inputs and the other pipeline commands are documented in the [ETL guide](../etl/README.md)
and [flood/land-price guide](khoi-implementation.md).

Useful checks:

```sh
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/api/v1/population/years
curl http://localhost:8080/api/v1/floods/history
```

## Backend API contract

All API routes are under `/api/v1`. GeoJSON coordinates and query bounds use
WGS84/EPSG:4326 and `[longitude, latitude]` order. Bboxes use
`west,south,east,north`. Successful layer-feature responses are GeoJSON
`FeatureCollection` objects with a `metadata` member; they are not wrapped in a
`data` envelope.

| Use | Endpoint |
| --- | --- |
| Discovery and OpenAPI | `/api/v1`, `/api/v1/openapi.json` |
| Layer catalog and availability | `/api/v1/layers` |
| GeoJSON features | `/api/v1/layers/{layer}/features?bbox=west,south,east,north&limit=...` |
| Vector tile metadata | `/api/v1/layers/{layer}/tilejson.json` |
| Mapbox vector tiles | `/api/v1/layers/{layer}/tiles/{z}/{x}/{y}.pbf` |
| Population catalog and loaded years | `/api/v1/population`, `/api/v1/population/years` |
| Population TileJSON and PNG tiles | `/api/v1/population/{year}/tilejson.json`, `/api/v1/population/{year}/tiles/{z}/{x}/{y}.png` |
| Population point sample | `/api/v1/population/{year}/value?lng=...&lat=...` |
| Population viewport statistics | `/api/v1/population/{year}/stats?bbox=west,south,east,north` |
| Historical floods | `/api/v1/floods/history` |
| Satellite flood classifications | `/api/v1/floods/satellite` |
| Rainfall-threshold risk indicators | `/api/v1/floods/risk`, `/api/v1/urban/flood` |
| Official land-price reference data | `/api/v1/land-prices`, `/api/v1/urban/land-price`, `/api/v1/layers/land_price/tiles/{z}/{x}/{y}.pbf` |
| HCMC land parcels | `/api/v1/layers/parcels/features`, `/api/v1/layers/parcels/tiles/{z}/{x}/{y}.pbf` |

The `population` layer contains persons per source raster cell (nominally
100 m), not people per square kilometre. Raster PNG tiles support
`pseudocolor`, `greyscale`, or `fire` palettes. Vector feature routes accept
`bbox`, `start`, `end`, and `limit` where the layer supports time filtering.

Interpret the flood products according to their metadata:

- `flood_history` is a set of reported observation points. Missing reports do
  not indicate that flooding did not occur.
- `flood_satellite` contains positive classified pixels clipped to the ETL
  boundary. It is not a complete flood-depth model.
- `flood_risk` is a rainfall-threshold indicator around historic flood
  locations, not a simulated flood extent or depth.
- Land-price features currently cover matched roads in An Khánh ward, with
  official 2026 reference prices matched by road name to OSM geometry. Current
  automatic matches use whole named-road geometry rather than clipping to the
  annex endpoints; they do not represent complete city coverage or verified
  legal price-segment geometry.

## Frontend dataset integration — 2026-10-06

- `frontend/src/services/api.ts`: typed, validated catalog/feature/statistics/
  point-sample requests. Requests have a 15-second timeout and cancellation.
  API error bodies are not displayed or logged. No server credentials are used.
- `frontend/src/features/map/datasets/`: catalog state, source lifecycle,
  dataset styles, controls and inspection. Tile templates use the configured
  public API base rather than absolute internal hosts from backend TileJSON.
  They follow the documented XYZ contract: max zoom 18, MVT source-layer
  `features`, population tiles 256 px with bounds `[102,8,110,24]`.
- Population offers only loaded years; default is the latest loaded year not
  later than the current calendar year (otherwise latest available). Future
  years remain explicitly selectable. Palette legend stops mirror
  `backend/app/services/raster_tiles.py`; keep them synchronized if palettes
  change. Units are people/source cell, never density/km².
- Flood history, satellite and risk have independent toggles. Risk colors are
  categorical: orange rain alert, teal below rainfall threshold, grey unknown.
  Teal does **not** assert an area is flood-safe. Expired catalog data is marked.
- Flood date controls default to **All dates**; start is inclusive and end is
  exclusive at midnight UTC. The existing map time-range control is not silently
  applied to historic datasets. Land price is not time-filtered by this API.
- Land price accepts reviewed geometry or explicitly published automatic
  whole-named-road proxies. Empty/unpublished snapshots stay disabled. Automatic
  matching and geometry-coverage caveats appear in the legend details and feature
  inspection. Prices are official reference VND/m², not transaction prices.
  The catalog renderer owns this overlay; the standalone Land price adapter is
  used only without a backend bridge, avoiding duplicate layers and popups.
- HCMC parcels use the backend vector-tile source and catalog availability.
  The layer begins requesting/rendering tiles at zoom 16, avoids per-pan
  GeoJSON/count probes, and opens the parcel's allowlisted cadastral attributes
  on click. Its source attributes do not establish ownership or legal status.
- Raster/MVT sources load only when enabled. Opacity updates do not recreate
  sources. Year/palette/date changes replace the relevant source; style changes
  restore overlays below symbols, buildings and measurement/Viewshed custom
  layers. Removal/unmount aborts viewport requests and removes owned layers and
  sources. No measurement geometry, picking, terrain or building cache changed.
- A debounced settled-viewport check uses GeoJSON `bbox` plus `limit=1` for
  vector presence, and population statistics only for viewports ≤4 square
  degrees. Large population views say **Zoom in to inspect coverage** instead
  of issuing an expensive/invalid statistics request. Empty data is distinct
  from loading and failure; retry refreshes catalog and sources. HTTP 204 tiles
  are valid empty content in the installed MapLibre version.
- Outside active measuring/Viewshed, clicking a vector overlay shows allowlisted
  feature properties; clicking population samples its source cell. Late requests
  are cancelled and labels are escaped React text, not backend HTML. The
  inspection closes when the dataset selection changes or a tool takes control.

### Local frontend development

The Data layers drawer groups supported backend datasets first, local POI/3D
display controls separately, and future integrations under **More layers**.
Availability and population-year counts come from the catalogs, not the aggregate
`/ready.loaded_layers` count (which can include products not rendered by this UI).
Active layers reveal controls and legends; explanatory caveats are available via
**About this data**. A fixed header retains refresh/close controls while the body
scrolls. The UI reuses the existing light-glass/teal/system-font tokens and motion,
including keyboard focus and reduced-motion handling. No renderer/API behavior
was changed by this UI refinement. The user's current backend proxy is reached
through an SSH tunnel at `http://localhost:51873`; the tunnel must be running for
live catalogs and tiles to load.

Keep `VITE_API_BASE_URL=` empty in `frontend/.env.local` to use the same-origin
proxy. Vite forwards `/api` to the Compose proxy at `http://127.0.0.1:8080` by default. When using an
existing Compose frontend or SSH tunnel instead, set its address before starting
Vite. `API_PROXY_TARGET` can be set in `frontend/.env.local` (dev-server only, not
exposed to the browser) or overridden in the shell, for example in PowerShell:

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:51873'
cd frontend
npm run dev
```

Use the port where **your backend proxy actually listens**. Restart Vite after
changing environment settings. A nonempty `VITE_API_BASE_URL` bypasses the Vite
proxy and therefore needs a browser-reachable origin and appropriate existing
CORS configuration. Production Compose keeps using nginx unchanged.

### Verification and remaining dependencies

Unit tests cover malformed/error responses, loaded-year selection, independent
catalog failures, empty/unreviewed land-price gating and retry/date semantics.
`tests/browser/data-layers.spec.ts` runs the full App in isolated Chromium using
test-only PNG/MVT/API fixtures: all five overlays render, filters reach the API,
opacity preserves source identity, styles restore overlays, 204/404/503 are
handled, sources clean up and distance measurement retains click priority.

Live PostGIS verification still requires a running backend with ETL data. During
this implementation no API responded on local ports 8000, 8080 or 51873; fixture
tests are not evidence that a remote deployment is healthy. No ETL, database,
backend schema, deployment workflow or remote deployment was changed.

MapLibre reference: [source lifecycle API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/)
and [raster/vector source specification](https://maplibre.org/maplibre-style-spec/sources/).

`VITE_API_BASE_URL` is currently optional and defaults to an empty string. Keep
server-side credentials out of Vite variables; only the public Goong map-tile
key belongs in the browser bundle. The backend already supports the current
same-origin Compose proxy, so CORS is not needed for that path.

## Verification

### Deploy and parcels merge — 2026-10-06

- Application commit `8592442` passes the PostGIS integration workflow. Explicit
  SQL casts select the expression overload of `ST_MapAlgebra`; untyped literals
  previously selected the callback overload and caused Population PNG HTTP 503.
- Deploy run `37468390787` ships that fix and the catalog UI. Live checks through
  the SSH tunnel confirm `/ready` (4 layers, 16 population years), the new frontend
  bundle, and three neighbouring zoom-16 PNGs at 106.8/10.875, each 256×256 with
  no transparent edge pixels. Requests took about 2.7–2.9 seconds through the
  tunnel; this is not evidence that broader performance optimization is complete.
- The `feat/nguyen-hcmc-parcels` frontend integration was added afterward. Before
  deploying the parcels backend, run the protected database migration workflow for
  `03-parcels-hcmc.sql`, then explicitly load parcel data as needed. The new
  repository readiness query requires `parcels.loaded_tile`. No production
  migration or parcel ETL was run as part of the merge. The toggle stays disabled
  until the backend catalog reports loaded parcel tiles.

### Dataset rendering and location fixes — 2026-10-06

- Population tiles now retain a two-pixel halo (the larger of source/output
  pixel sizes) before reprojection, use
  one bilinear warp aligned to the XYZ reference, and explicitly pad/crop to
  256 × 256 pixels. This addresses clipped cell centres at tile edges and
  nearest-neighbour display blocks. Raw `/value` and `/stats` are unchanged.
  See PostGIS [reference-aligned raster transforms](https://postgis.net/docs/RT_ST_Transform.html)
  and [explicit output extents](https://postgis.net/docs/RT_ST_MapAlgebra_expr.html).
- Smoothing is a visualization, **not** higher-resolution population data.
  Nominal resolution remains 100 m. True no-data areas remain transparent;
  do not interpret every transparent road-shaped gap as a broken tile.
- PNG URLs use `render=2` and versioned ETags; Flood history MVT uses `schema=2`
  and versioned ETags. Rebuild/deploy **both backend and frontend**. A frontend
  restart alone cannot fix tiles served by the old remote backend. After rollout,
  hard-reload any browser that previewed the new frontend against the old API.
  No migration or ETL reload is required.
- Flood history previously lost nested administrative context in MVT. The API
  now exposes `reported_ward`, `reported_district`, and `current_admin_unit` from
  existing snapshot provenance, without modifying source geometry. UI normalizes
  Unicode/whitespace, avoids repeated address components, distinguishes historical
  reported locations from current source-listed wards, and labels area/street
  points as approximate rather than exact addresses.
- Verified against the currently loaded records: `Obs_208` (2007-11-25,
  Hiệp Bình Chánh/khu phố 3) is an **Area point / Medium**; `Obs_329`
  (2019-04-09, Cầu Ông Dầu) is an **Area point / Low**. Both list the current
  administrative unit as Phường Hiệp Bình. Their original coordinates and depths
  are intentionally unchanged. Exact relocation requires reviewed source evidence;
  this change does not claim to repair uncertain source geocoding.
- Data layers removes duplicate Ready/On states and per-row descriptions. Unit
  legends, availability, errors/retry and coverage hints remain. Caveats are under
  **Details**. Existing light-glass style, keyboard access and animations remain.

Regression coverage: `backend/tests/test_raster_alignment.py` includes adjacent
XYZ tiles at zoom 14/18 across source chunk boundaries. Run with `POSTGIS_TESTS=1`
and `WAREHOUSE_*` pointing to a **test database** with PostGIS raster enabled.
The new raster tests use TEMP fixtures and rollback, not production data writes.
Without a local PostGIS instance these integration cases are explicitly skipped;
API/query-contract unit tests are not a substitute for that deployment gate.

Local verification for this change: frontend build/lint and 102 unit tests pass;
26 backend tests pass, with four PostGIS integration cases skipped (no local
PostGIS/Docker daemon). All five dataset/browser UI tests pass at 320–1440 px.
The broader browser suite passed 21/23: the Viewshed terrain check passed on an
isolated rerun, but the existing seven-metre road/camera test still timed out at
45 seconds in software WebGL. No road, terrain or measurement implementation,
assertion, or timeout was changed as part of this dataset fix. This broader
suite is therefore **not fully green**; retain that limitation during review.

With PostGIS, backend, and frontend running and local data loaded:

```sh
cd frontend
npm ci
npx playwright install chromium
npm run test:api:e2e
npm run test:map
```

`test:api:e2e` uses Chromium for a browser fetch and Playwright request checks
through the frontend proxy. It expects population plus flood history, satellite,
and risk data to be loaded. `test:map` uses mocked Goong/terrain fixtures and
checks the existing map/measurement UI and backend-layer rendering with isolated
fixtures. The optional `npm run test:map:live` needs working external map
services and a valid Goong key.

Backend tests are in `backend/tests`. See [backend operations](../backend/README.md)
for API details and [ETL operations](../etl/README.md) for pipeline-specific
inputs and commands.

Only enable a layer control after the frontend handles loading, empty, error,
and source/layer cleanup states for its backend endpoint.

## Area measurement update — 2026-10-05

The frontend now includes a world-anchored Area tool alongside Distance. See [area-measurement.md](area-measurement.md) for calculation rules, units, state/rendering lifecycle, limitations and verification. No new endpoint is required. Building height/DEM availability remains the key data dependency; visual fallback heights are not valid measurements. The picking cache now retries missing elevation and refreshes candidates after the scene settles without expanding the tile cache/LOD budget.

## Viewshed update — 2026-10-05

The ruler chooser also includes **Viewshed**: two-click observer/target placement,
3D translation handles, live directional visibility, numeric editing and multiple
retained analyses. See [viewshed.md](viewshed.md) for interaction, resource limits,
coverage/accuracy caveats and the future occluder-data integration boundary.
This implementation analyzes loaded terrain and supported building geometry; it
does not claim complete regional coverage or infer unknown heights. No new backend
endpoint is required, and existing distance/area calculations are unchanged.

## Frontend update — 2026-10-06

- Data layers now has **Points of interest**, enabled by default. The `poi` layer
  state controls POI symbol visibility only (Goong `poi-*` IDs; POI source-layer
  fallback). Road/city names, measurement markers and user location remain intact.
  Original provider-hidden POIs stay hidden. The choice survives 2D/3D and basemap
  changes during the session. Raster-only satellite has no independent POI overlay;
  text baked into imagery cannot be hidden with a vector-layer switch.
- Uses MapLibre's [layout visibility API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#setlayoutproperty),
  with no new API, data fetch, dependency or backend/schema change.
- Area keeps its calculations, units and warnings; New is now a compact labelled
  icon. Viewshed exposes range/FOV summary and folds advanced numeric fields under
  **Adjust view**. Existing GSAP entrance and reduced-motion handling are reused.
- Viewshed target arrows edit heading, tilt and distance independently. Four
  far-plane edges resize horizontal/vertical FOV without moving endpoints. See
  [Viewshed interaction/limits](viewshed.md). Occlusion classification is unchanged.
