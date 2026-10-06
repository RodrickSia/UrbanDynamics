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
- **The React map UI is not yet connected to these datasets.**
  `frontend/src/services/api.ts` lists endpoint paths but is not imported by the
  UI. The layer controls remain integration points; the browser E2E checks call
  the APIs but do not add these sources to the MapLibre map.
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
| Reviewed land-price segments | `/api/v1/land-prices`, `/api/v1/urban/land-price` |

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
- Land-price geometry/values must be reviewed before publishing. An unavailable
  layer returns an API error rather than placeholder features.

## Frontend integration work remaining

1. Replace the unused endpoint list in `frontend/src/services/api.ts` with
   typed request helpers for the implemented routes. Prefer `/api/v1/...`
   same-origin URLs when running behind Compose nginx.
2. Load the population catalog and add its XYZ PNG template as a MapLibre raster
   source/layer. Add year and palette controls, loading/empty/error states, and
   remove/recreate the source cleanly when selection changes.
3. Add flood history, satellite, and risk as vector-tile sources where possible;
   use GeoJSON endpoints for feature inspection or small filtered views. Give
   each product a legend that matches its meaning and metadata.
4. Keep land-price UI disabled until reviewed segment data is published. Do not
   treat the extracted PDF rows or unreviewed full-road OSM candidates as
   approved segment geometry.
5. Add UI tests for enabled/disabled layer controls, time/bbox filters, empty
   results, API failures, and source cleanup when switching styles or layers.

`VITE_API_BASE_URL` is currently optional and defaults to an empty string. Keep
server-side credentials out of Vite variables; only the public Goong map-tile
key belongs in the browser bundle. The backend already supports the current
same-origin Compose proxy, so CORS is not needed for that path.

## Verification

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
checks the existing map/measurement UI; it does not test backend layer
rendering. The optional `npm run test:map:live` needs working external map
services and a valid Goong key.

Backend tests are in `backend/tests`. See [backend operations](../backend/README.md)
for API details and [ETL operations](../etl/README.md) for pipeline-specific
inputs and commands.
