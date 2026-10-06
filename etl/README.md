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

The manual GitHub workflow prepares this boundary from the published DataSuds
boundary dataset when it is missing. For local runs, prepare it once with
`scripts/prepare-khoi-data.py boundary` and store it under
`etl/data/inputs/thu_duc_boundary.geojson`.

Compose passes the selected pipeline through `ETL_PIPELINE`. From the ETL
directory, the CLI can also be invoked directly, for example:

```sh
python -m src.main run flood_history --stage all \
  --boundary /app/data/inputs/thu_duc_boundary.geojson
```

The manual GitHub Actions workflow offers pipeline choices and `all` / `extract`
stage choices. Its **all** choice runs eligible full pipelines sequentially in
this order: population, flood history, flood satellite, flood risk, and land
price. If rainfall inputs are missing, it downloads forecast/history from
Open-Meteo for one integration point. If land-price inputs are missing, it
downloads and parses the official annex and fetches OSM road candidates. The
boundary is also prepared automatically. Flood risk can then run; land-price
publishing remains skipped until a person reviews the candidate geometry and
price values. Selecting all pipelines requires stage `all`. Parcel ETL also
supports independent `transform` and `load` stages; other pipelines require
their full pipeline to execute those steps.

## Warehouse and data

ETL containers connect to the main PostGIS warehouse at `postgis:5432` using
`WAREHOUSE_*` settings. They do not publish host ports or create database
tables. Population TIFFs load into `population.population_raster`; flood and
land-price GeoJSON features publish as atomic full-layer snapshots in
`public.layer_snapshots` and `public.layer_features`. HCMC cadastral plots
load into `parcels.land_plot` from public vector tiles under
`etl/data/parcels_hcmc`. Run that pipeline with
`docker compose --profile etl-parcels-hcmc run --rm etl-parcels-hcmc`.
It does not download listing prices.
For an already downloaded tile tree, the parcel ETL can also run the stages
separately with `--stage transform` (validate the XYZ tile tree) and
`--stage load` (decode and stream the saved tiles to PostGIS). This avoids
re-fetching tiles when only the database load needs to be completed.

All pipeline services share the host directory `etl/data/`. Flood risk reads a
previously published `flood_history` layer and forecast/history JSON from
`etl/data/inputs/`. Land-price publication automatically matches extracted rows
to OSM roads by normalized name using
`etl/data/review/land_price_auto_segments.geojson`. These geometries represent
whole named roads; they are not clipped to the official price table endpoints.

Flood-risk requires forecast and history rainfall files under
`etl/data/inputs/`; the repository does not provide a standalone rainfall
pipeline.
