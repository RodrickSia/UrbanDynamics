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
building footprints and parcel-based model generation. Its **all** choice runs eligible full pipelines
sequentially in this order: population, flood history, flood satellite, flood
risk, land price, HCMC cadastral parcels, HCMC Overture footprints, HCMC GBA
LoD1 buildings, and parcel-based model generation. If rainfall inputs are missing,
it downloads forecast/history from Open-Meteo. Land-price source rows and OSM
road candidates are prepared automatically. Selecting all pipelines requires
stage `all`. Parcel and buildings-footprint ETL support separate
`transform` and `load` stages. Model generation runs last when parcel and GBA
source data are available.

`model_generation` runs after the parcel and GBA source datasets are available.
It selects eligible residential parcels regardless of building-footprint
overlap, insets each parcel outline, and samples a height from the observed GBA
residential-height distribution. It replaces `buildings.synthetic_residential`
in one transaction. The backend
serves this table as `synthetic_buildings` vector tiles; the frontend renders
the layer in 3D. These are approximate models, not surveyed building outlines
or heights. Apply the `20261013-model-generation.sql` migration before running it.

Run the pipeline independently:

```sh
docker compose --profile etl-model-generation run --rm etl-model-generation run --stage all
```

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

Fetch the GlobalBuildingAtlas LoD1 models for HCMC independently:

```sh
docker compose --profile etl-buildings-footprint-gba run --rm etl-buildings-footprint-gba run --stage all
```

This uses the pinned `GBA.LoD1` HCMC tile (`asiawest/e105_n15_e110_n10`),
joins the published height and variance estimates to its building polygons,
transforms the tile from EPSG:3857, and clips it to the same expanded HCMC
boundary used by the Overture pipeline. The source files are large (about
14.6 GB combined); downloads resume from partial files and are cached under
`etl/data/buildings_footprint_gba/`. Use `--refresh` to fetch the pinned files
again. The stages can be run separately: `extract` downloads, `transform`
clips and joins heights, and `load` publishes the saved GeoJSON to PostGIS.
The `all` ETL workflow includes this pipeline, so selecting `all` also fetches
the large GBA tile.

GBA records are stored separately in `buildings.gba_lod1`; they never replace
the Overture snapshot in `buildings.footprint`. Height estimates and their
variance are approximate model outputs, not surveyed measurements. The
`GBA.LoD1` data is distributed under CC BY-NC 4.0, which restricts commercial
use. The `05-buildings-gba-lod1.sql` and
`06-buildings-gba-feature-id.sql` migrations create and key its table;
apply migrations through the protected database deployment workflow before
running this pipeline.

Generate inset residential building extrusions from parcels after the parcel
and GBA datasets are loaded:

```sh
docker compose --profile etl-model-generation run --rm etl-model-generation run --stage all
```

The pipeline inventories all parcel land-use values, uses only the explicit
residential codes `OTC`, `ODT`, and `ONT` without filtering for existing
building-footprint overlap, and samples model heights from GBA
buildings on residential parcels. It publishes the synthetic models separately
to `buildings.synthetic_residential`. The `20261013-model-generation.sql`
migration creates that table; apply it with the protected database deployment
workflow. Extracted inventory and stage files are stored in
`etl/data/model_generation/`.

Build an OSM-derived SUMO road network for HCMC and publish it to PostGIS:

```sh
docker compose --profile etl-osm-sumo-hcmc run --rm etl-osm-sumo-hcmc run --stage all
```

The pipeline downloads Geofabrik's Vietnam PBF, crops it to an expanded HCMC
bounding box, runs SUMO `netconvert`, then transactionally replaces
`transport.sumo_edge`, `transport.sumo_junction`, and
`transport.sumo_connection`. Edge and junction geometries are transformed back
to WGS84. Input/output files are cached under `etl/data/osm_sumo_hcmc/`;
`extract`, `transform`, and `load` can also run separately. Apply
`07-sumo-road-network.sql` before loading. This produces a starting road graph,
not calibrated traffic demand: verify lane counts, speed limits, turns, and
signals against local data before interpreting simulation results. The
bounding-box crop includes fringe roads and is not an administrative HCMC
boundary.

Load the checked-in historical traffic CSV and match its road-segment
observations to the SUMO network:

```sh
docker compose --profile etl-traffic-history run --rm etl-traffic-history run --stage all
```

The source file is `etl/data/traffic_history/traffic.csv`. The transform stage
normalizes its date and 30-minute `period` into `observed_at`, preserves LOS and
the sparsely populated `max_velocity` field without assuming it is observed
traffic speed, and writes `traffic_observations.csv`. The load
stage matches source node pairs first, then uses a 40 m spatial search against
`transport.sumo_edge`; results, including unmatched source rows, are upserted to
`transport.traffic_observation`, replacing that pipeline's previous snapshot on
each run. Apply `07-sumo-road-network.sql` and then
`08-traffic-history.sql` before loading. This records observed conditions for
analytics and calibration; it does not infer vehicle counts, measured speeds,
or generate SUMO routes/demand.

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
