# UrbanDynamics

UrbanDynamics is an urban-data platform for exploring cities in Vietnam. It
combines a web map, a FastAPI service, a PostGIS warehouse, and ETL pipelines for
publishing spatial datasets. Its planning tools support scenario analysis; their
outputs are modeled results, not forecasts or official determinations.

## Development simulation preview — this branch

`feat/development-simulation-context` extends main's Development workflow with
preserved/sourced ground cover, cached local OSM road context, explicit background
traffic assumptions, and Before / After / Change tables with SUMO delay and queue.

The separate server preview is available at **http://127.0.0.1:8192** through the
workstation SSH tunnel (server 156, loopback port **51875**). Open **Plans →
Simulation context demo · Thu Duc parcel 1937203 → Development**, then select the
saved apartment proposal. Production main is not replaced. Plans and simulation
results use a separate volume; the team warehouse is read-only.
Use **View last completed run** to open the prepared SUMO/SWMM case immediately.

See [the implementation and usage guide](docs/development-simulation-context.md)
for data sources, synthetic assumptions, local ports, deployment and verification.

## What is included

- An interactive React, TypeScript, and MapLibre map with 2D/3D views and
  available urban layers.
- A FastAPI backend that serves map data, population, flood and rainfall
  indicators, land-price references, parcels, zoning, and planning scenarios.
- A PostGIS/PostGIS Raster warehouse with versioned SQL migrations.
- ETL pipelines for population, flood datasets, land prices, HCMC parcels and
  buildings, and an OSM-derived SUMO road network with historical traffic
  observations.
- A background planning worker for computational planning scenarios.

The existence of a dataset or ETL pipeline does not mean it is already loaded
in your database or connected to a frontend layer. Traffic has separate map
layers for a historical congestion profile, the static SUMO network, and
standalone SUMO scenario output. The SUMO runner derives estimated demand from
historical LOS because the available sources do not provide calibrated vehicle
counts or observed OD routes. Treat its results as modeled scenarios, not
validated forecasts.

## Architecture

```text
frontend (React / MapLibre)  →  backend (FastAPI)  →  PostGIS warehouse
                                      ↑                       ↑
                              planning worker          ETL pipelines
```

The root `compose.yaml` defines the application stack. ETL services are opt-in
Compose profiles. The frontend is published on port `8080` by default; the
database is available to Compose services at `postgis:5432` and is not exposed
on a host port by default.

## Quick start

Requirements: Docker with the Compose plugin, and a Goong Map Tiles key if you
want the configured basemap.

1. Create local configuration and set a unique database password:

   ```sh
   cp .env.example .env
   ```

   Edit `.env` and set `WAREHOUSE_PASSWORD`. Optionally set
   `VITE_GOONG_MAPTILES_KEY` and `FRONTEND_PORT` (default `8080`). The map-tile
   key is embedded in the browser build, so use only a browser-restricted public
   key there; never put a Goong REST secret in a `VITE_*` variable.

2. Start the application:

   ```sh
   docker compose up --build -d
   ```

3. Open [http://localhost:8080](http://localhost:8080). Check service status
   with `docker compose ps` and view logs with `docker compose logs -f backend`.

On a new warehouse, Compose initializes the database and applies its migrations.
For an existing warehouse, apply pending migrations before running ETL:

```sh
WAREHOUSE_MIGRATION_TARGET=compose sh infra/warehouse/scripts/migrate.sh
```

See [`infra/warehouse/README.md`](infra/warehouse/README.md) for migration,
credential, and database deployment details. Changing `.env` does not rotate
the password stored in an already initialized database volume.

## API

The backend exposes its OpenAPI documentation at `/api/v1/docs` inside the
backend service. The frontend's same-origin proxy routes API requests to the
backend. Health endpoints are `/health` and `/ready`.

Backend route groups include population, floods, land prices, parcels, zoning,
urban layers, area indicators, weather, and planning. See
[`backend/README.md`](backend/README.md) for local development and the API
details.

## Data pipelines

ETL source data and generated files are kept under `etl/data/` by default and
mounted into containers at `/app/data`. Large or licensed source datasets may
need to be obtained separately; a pipeline being present does not guarantee its
input files are checked into Git. Check the pipeline documentation and data
license before downloading or publishing data.

For example, after the warehouse is running and migrations are current, run
the HCMC SUMO network pipeline with:

```sh
docker compose --profile etl-osm-sumo-hcmc run --rm \
  etl-osm-sumo-hcmc run --stage all
```

The historical traffic pipeline loads its checked-in CSV and matches road
observations to the published SUMO network:

```sh
docker compose --profile etl-traffic-history run --rm \
  etl-traffic-history run --stage all
```

These commands populate warehouse data; they do not create SUMO demand. The
separate SUMO congestion simulation can be started from the map's Data layers
sidebar after applying migrations `11-sumo-congestion-simulation.sql` and
`12-sumo-congestion-scenario-cache.sql` and
starting the `traffic-prediction-worker` Compose service. For its assumptions
and the resumable 336-scenario cache workflow, see [`backend/README.md`](backend/README.md). For the available
ETL profiles and input limitations, see [`etl/README.md`](etl/README.md). For
frontend development commands, see
[`frontend/README.md`](frontend/README.md).

## Development and checks

Frontend:

```sh
cd frontend
npm ci
npm run dev
npm test
npm run lint
npm run build
```

Backend and warehouse integration tests are documented in
[`backend/README.md`](backend/README.md). Database migrations and isolated CI
checks are described in [`infra/warehouse/README.md`](infra/warehouse/README.md).

## Repository layout

```text
backend/              FastAPI application and planning services
frontend/             React/TypeScript map application
etl/                  ETL pipelines, source data, and pipeline documentation
infra/warehouse/      PostGIS image, migrations, and migration runner
scripts/              Shared operational and data-preparation scripts
.github/workflows/    CI and protected deployment workflows
compose.yaml          Main local application and ETL service definitions
```

## Data, credentials, and limitations

- Do not commit credentials, `.env` files, or private API keys. Use GitHub
  environment secrets for protected deployments.
- Check source attribution, license, geographic coverage, and update date for
  each dataset before relying on or redistributing it.
- Population, flood, rainfall, building-height, and planning outputs have
  dataset- and model-specific uncertainty. They are not substitutes for
  authoritative or field-verified information.
- Simulation is only as useful as its inputs and calibration. The OSM-derived
  SUMO network is a starting road graph; observed LOS and sparse speed fields
  do not establish traffic demand or validate a congestion forecast.
