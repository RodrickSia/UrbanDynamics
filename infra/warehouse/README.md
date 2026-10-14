# PostGIS warehouse

Compose builds the warehouse image from this directory. It uses PostgreSQL 17
with PostGIS and PostGIS Raster extensions. Database files live in the
persistent `postgis_data` volume. Compose does not publish a host port for the
database; containers connect to `postgis:5432` on the internal network.

## Data model

- Population rasters: `population.population_raster`.
- Flood and land-price vector snapshots: `public.layer_snapshots` and
  `public.layer_features`.
- Overture building footprints: `buildings.footprint` and
  `buildings.snapshot_metadata`.
- Applied migrations: `public.schema_migrations`.

Schema changes are numbered SQL files in `migrations/`. Empty database
initialization runs the migrations automatically. For an existing database,
start PostGIS and apply pending migrations with:

```sh
WAREHOUSE_MIGRATION_TARGET=compose sh infra/warehouse/scripts/migrate.sh
```

The runner applies each migration and its ledger entry in one transaction, and
skips versions already recorded. The manual `Deploy database` workflow invokes
the same runner against the production Compose warehouse without replacing its
database volume.

The standalone SUMO congestion-prediction queue is created by
`11-sumo-congestion-simulation.sql`. Apply that migration before starting runs
from the map; the separate `traffic-prediction-worker` consumes queued jobs.

## Configuration and credentials

Copy `.env.example` to `.env` and set a unique `WAREHOUSE_PASSWORD` before the
first PostGIS initialization. `WAREHOUSE_DATABASE` and `WAREHOUSE_USER` can
override their documented defaults. An empty password cannot initialize a new
database, and changing `.env` does not rotate credentials in an existing
volume. Coordinate password rotation with the database administrator and
update the GitHub `production` environment secret to match. Never remove the
database volume as a password-rotation method.

Frontend-only and backend-only image builds do not need the warehouse password.
CI uses an ephemeral password for its isolated database. Production database
and application workflows use the protected GitHub `production` environment;
configure its `WAREHOUSE_PASSWORD` secret and required reviewers.

Database CI starts a fresh PostGIS image and checks the extensions, tables, and
migration ledger. The separate integration workflow runs the flood, land-price,
and API tests against an isolated database on the Compose network.
