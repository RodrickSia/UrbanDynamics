# UrbanDynamics API

The backend is an isolated FastAPI service. Compose connects it to PostGIS on
the private Docker network as `postgis:5432`; only the frontend publishes a
host port. `backend/Dockerfile` builds from the repository root and installs
the locked backend dependencies with `uv`.

## API discovery

- Interactive docs: `/api/v1/docs`
- OpenAPI document: `/api/v1/openapi.json`
- API index: `/api/v1`
- Health and readiness: `/health` and `/ready`
- Layer catalog: `/api/v1/layers`

Coordinates and GeoJSON use WGS84 / EPSG:4326 in `[longitude, latitude]`
order. Spatial query bboxes use `west,south,east,north`.

## Map endpoints

| Data | API |
| --- | --- |
| Flood, satellite, and land-price GeoJSON | `/api/v1/layers/{layer}/features?bbox=west,south,east,north&start=...&end=...&limit=...` |
| Mapbox vector tiles | `/api/v1/layers/{layer}/tiles/{z}/{x}/{y}.pbf` |
| Vector tile metadata | `/api/v1/layers/{layer}/tilejson.json` |
| Population years and source metadata | `/api/v1/population/years` |
| Population XYZ PNG tiles | `/api/v1/population/{year}/tiles/{z}/{x}/{y}.png?palette=pseudocolor` |
| Population point sample | `/api/v1/population/{year}/value?lng=106.7&lat=10.8` |
| Population viewport statistics | `/api/v1/population/{year}/stats?bbox=west,south,east,north` |
| Historical weekday/time traffic congestion layer | `/api/v1/traffic/prediction` |
| Cached SUMO weekday/time scenario | `/api/v1/traffic/sumo-simulations/scenarios/{weekday}/{period}` |
| Standalone SUMO congestion runs | `POST /api/v1/traffic/sumo-simulations/runs` |
| SUMO run status and map GeoJSON | `/api/v1/traffic/sumo-simulations/runs/{run_id}` and `/features` |

The vector catalog exposes layer availability, geometry types, fields, source
metadata, and known limitations. Flood history is reported point observations
with depth and source attributes; satellite polygons mean positive flood
pixels, not verified dry areas; flood risk polygons are heuristic rain
indicators around historical events, not simulated flood extent or depth.
Land-price GeoJSON and vector tiles come from the same PostGIS snapshot. The
original land-price demo contained official 2026 An Khánh ward reference
prices matched by normalized road name to OpenStreetMap road geometry.
Actual coverage depends on the loaded ETL snapshot. Coverage can be partial;
legacy name-only matches use whole named-road geometry and are not clipped to
the annex's intersection-to-intersection price segments. These
are statutory reference prices, not transaction or asking prices. Feature
properties include the source URL, effective date, unit, matching mode,
geometry coverage, and annex page where available.

Parcel details can return a `provisional` road-price association up to 40 m
from the parcel when the published road segment is unique and spatially checked.
For source land-use code `L`, explicit apartment-planning metadata can supply
the Residential category with `classification_basis: planning` and low
confidence. Provisional associations expose only the reference unit price;
`estimated_land_total_vnd` remains null. Missing or ambiguous road prices also
remain null.

Population values are persons per source raster cell. The service does not
claim population density per square kilometer. The source rasters are stored
in `population.population_raster`, while vector snapshots remain in
`public.layer_snapshots` and `public.layer_features`.
Population PNG rendering is done in the API process from resampled pixel
values, so it does not require enabling GDAL output drivers in PostGIS.

The standalone SUMO traffic predictor is separate from development/zoning
simulation. It queues a weekday/30-minute run to the `traffic-prediction-worker`
Compose service, builds/caches a SUMO road network from the HCMC OSM PBF, and
returns edge-level simulated speeds and LOS for the map. It derives one global
random-trip rate from historical LOS because the current traffic sources do
not provide vehicle counts or an observed origin-destination matrix. Treat the
result as an estimated-demand scenario, not a validated forecast. The map
includes all network road edges and colors them by SUMO-estimated passenger-car
passages over the simulated 30-minute interval. To keep batch runs fast, this
scenario simulates passenger cars only; its demand rate preserves the configured
30% car share but motorcycle interactions are not modeled. It uses SUMO's
mesoscopic queue model (`--mesosim true`) for throughput; this is less detailed
than microscopic vehicle-following and lane-changing. Cache lookups are model
versioned, so previously cached microscopic scenarios are recomputed. Apply
`11-sumo-congestion-simulation.sql` and `12-sumo-congestion-scenario-cache.sql`
before using the queue API. The `Precompute SUMO traffic scenarios` workflow
queues all 336 weekday/half-hour combinations and stores completed GeoJSON
results compressed in PostGIS. It is resumable: rerunning it skips cached
scenarios and retries failed or unfinished ones. The map checks this cache
first; on a cache miss, it queues the selected scenario through the worker and
that result is added to the same cache for later requests. The precompute workflow
prepares the HCMC SUMO network once in the shared Compose runtime volume before
starting scenario workers. Network conversion has a 30-minute limit by default
(`TRAFFIC_NETWORK_BUILD_TIMEOUT_SECONDS`); once created, workers reuse the
network instead of rebuilding it per scenario. The workflow defaults to four
parallel workers and offers 1/2/4/8-worker choices; select a count appropriate
for the self-hosted VM's available CPU and memory.

## Configuration and operation

Set `WAREHOUSE_DATABASE`, `WAREHOUSE_USER`, and `WAREHOUSE_PASSWORD` through
the Compose environment. The backend uses the same connection settings as ETL
and does not run migrations. Apply warehouse migrations using the existing
database migration runner/workflow. Optional browser origins may be listed in
`BACKEND_CORS_ORIGINS` as a comma-separated environment variable; same-origin
frontend proxy requests need no CORS configuration.

For a local run, enter `backend/`, install with `uv sync --frozen`, then run
`uv run uvicorn app.main:app --reload`. Configure
`WAREHOUSE_HOST=localhost` when running outside Compose.
