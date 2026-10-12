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
| GBA LoD1 building snapshot | `/api/v1/buildings/snapshot` |
| GBA LoD1 building vector tiles | `/api/v1/buildings/tiles/{z}/{x}/{y}.pbf` |

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

The 3D building tiles read the `buildings.gba_lod1` snapshot added by the GBA
ETL on `main`. Only footprints with a positive `height_m` are extruded; the
frontend reports the model unavailable until a loaded snapshot contains such
buildings. Tiles are native at zoom 14–16 and overzoom at closer views. The
GBA model carries CC BY-NC 4.0 terms; the map attributes that source.

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
