# ETL

Each data domain has a pipeline under `src/pipelines/`. Pipeline-specific
configuration, models, extraction, transformation, and loading stay together;
shared warehouse and spatial helpers live in `src/shared/`.

## Run with Compose

Copy `.env.example` to `.env`, set `WAREHOUSE_PASSWORD`, and start PostGIS. Apply
pending database migrations before publishing data. Each pipeline has its own
Compose profile and service; all use the shared ETL image and mount `etl/data/`
at `/app/data`.

For example, run the population pipeline:

```sh
docker compose --profile etl-population-hcmc run --rm etl-population-hcmc run --stage all
```

Run flood history with a prepared WGS84 boundary:

```sh
docker compose --profile etl-flood-history run --rm etl-flood-history \
  run --stage all --boundary /app/data/inputs/thu_duc_boundary.geojson
```

Compose passes the selected pipeline through `ETL_PIPELINE`. From the ETL
directory, the CLI can also be invoked directly, for example:

```sh
python -m src.main run flood_history --stage all \
  --boundary /app/data/inputs/thu_duc_boundary.geojson
```

The manual GitHub Actions workflow offers pipeline choices and `all` / `extract`
stage choices. `transform` and `load` are not yet supported as independent CLI
stages; run the full pipeline to execute those steps.

## Warehouse and data

ETL containers connect to the main PostGIS warehouse at `postgis:5432` using
`WAREHOUSE_*` settings. They do not publish host ports or create database
tables. Population TIFFs load into `population.population_raster`; flood and
land-price GeoJSON features publish as atomic full-layer snapshots in
`public.layer_snapshots` and `public.layer_features`.

All pipeline services share the ignored host directory `etl/data/`. Flood risk
reads a previously published `flood_history` layer and forecast/history JSON
from `etl/data/inputs/`. Land-price publication requires reviewed road-segment
geometry in `etl/data/review/land_price_reviewed.geojson`.

Rainwater is listed in the CLI and manual workflow, but that pipeline is still
unfinished. Do not treat it as a working extraction or warehouse loader yet.
