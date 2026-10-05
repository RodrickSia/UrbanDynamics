# PostGIS warehouse

Compose builds the database image from this directory. It uses the PostGIS
PostgreSQL 17 image, enables the `postgis` and `postgis_raster` extensions on
first initialization, and stores database files in the persistent `postgis_data`
volume.

Configure `WAREHOUSE_DATABASE`, `WAREHOUSE_USER`, and `WAREHOUSE_PASSWORD` in
`.env` (see `.env.example`). Containers connect to host `postgis` on port `5432`;
host tools connect to `localhost` using `WAREHOUSE_FORWARD_PORT`.

The SQL scripts in `init/` run only when PostgreSQL initializes an empty data
directory. Use versioned migrations for schema changes after initialization.
