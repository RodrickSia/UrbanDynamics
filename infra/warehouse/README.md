# PostGIS warehouse

Compose builds the database image from this directory. It uses the PostGIS
PostgreSQL 17 image, enables the `postgis` and `postgis_raster` extensions on
first initialization, and stores database files in the persistent `postgis_data`
volume. Versioned SQL migrations are recorded in `public.schema_migrations`.

Configure `WAREHOUSE_DATABASE`, `WAREHOUSE_USER`, and `WAREHOUSE_PASSWORD` in
`.env` (see `.env.example`). Containers connect to host `postgis` on port `5432`;
host tools connect to `localhost` using `WAREHOUSE_FORWARD_PORT`.

There is no shared default password. Set a unique `WAREHOUSE_PASSWORD` in your
untracked `.env` before initializing PostGIS; an empty password is rejected by
the database image for a fresh data directory. Frontend/backend-only builds do
not require a warehouse password. CI creates an ephemeral random password.
Changing `.env` does not rotate the password in an existing database volume:
coordinate database credential rotation with its administrator and update the
GitHub `production` environment secret to match. Never delete the volume to
change a password. If the former committed default was used on a real server,
treat it as exposed and rotate it before deploying again.

The extension setup in `init/` and versioned migrations in `migrations/` run
automatically when PostgreSQL initializes an empty data directory. For an
existing database, start the PostGIS service and run
`WAREHOUSE_MIGRATION_TARGET=compose sh infra/warehouse/scripts/migrate.sh`.
The script applies each numbered migration once and records it in the migration
ledger. The `Deploy database migrations` GitHub Actions workflow runs the same
script against the already-running Compose database without rebuilding or
restarting the database container. Configure the GitHub `production` environment
with required reviewers and a `WAREHOUSE_PASSWORD` secret to gate this workflow.
Set `WAREHOUSE_DATABASE` and `WAREHOUSE_USER` as environment variables if their
names differ from the defaults. Keep each migration transactional; the runner
applies each SQL file and its ledger entry in one transaction.

Database CI builds a fresh PostGIS image, starts an empty database, and checks
that the extensions, population raster table, and migration ledger are present.
