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
stage choices for most pipelines, plus `transform` / `load` for parcels and
building footprints. Its **all** choice runs eligible full pipelines
sequentially in this order: population, flood history, flood satellite, flood
risk, land price, and HCMC building footprints. If rainfall inputs are missing,
it downloads forecast/history from Open-Meteo. Land-price source rows and OSM
road candidates are prepared automatically. Selecting all pipelines requires
stage `all`. Parcel and buildings-footprint ETL support separate
`transform` and `load` stages.

Run Overture building footprints independently:

```sh
docker compose --profile etl-buildings-footprint run --rm etl-buildings-footprint run --stage all
```

The pipeline reads the pinned Overture `buildings/building` release using a
bounding-box prefilter, then clips footprints to the checked-in expanded HCMC
boundary. It fetches building features, not building parts. Source Parquet is
cached under `etl/data/buildings_footprint/`; use `--refresh` to fetch the
pinned release again. Extraction and transformation can also run separately
with `--stage extract` and `--stage transform`; `--stage load` loads normalized
Parquet without contacting Overture.

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

Buildings are bulk-loaded into `buildings.footprint`, with source release,
attributes, and MultiPolygon geometry, and a latest-import record in
`buildings.snapshot_metadata`. The load stages rows into a temporary table and
replaces the previous snapshot in one transaction, so a failed import leaves
the last successful dataset intact. The `04-buildings-footprint.sql` migration
creates these tables and spatial indexes; apply it through the existing
database deployment workflow before running the pipeline.

The checked-in HCMC boundary is from the Vietnamese Provinces Database GIS
dataset, revision `86361845ba60ee779905ef07f04d7db33c798d04`. Its maintainers
say the geometry derives from the Vietnam Administrative Units Reference Map
published by the Ministry of Agriculture and Environment's mapping publisher.
The source repository is MIT licensed and is not a government agency.

All pipeline services share the host directory `etl/data/`. Flood risk reads a
previously published `flood_history` layer and forecast/history JSON from
`etl/data/inputs/`. Land-price publication automatically matches extracted rows
to OSM roads by normalized name using
`etl/data/review/land_price_auto_segments.geojson`. These geometries represent
whole named roads; they are not clipped to the official price table endpoints.

Flood-risk requires forecast and history rainfall files under
`etl/data/inputs/`; the repository does not provide a standalone rainfall
pipeline.
