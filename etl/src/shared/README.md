# Shared ETL helpers

Keep only cross-pipeline infrastructure here, such as download utilities,
spatial validation, logging, and warehouse access. Source-specific behavior,
configuration, and data models belong in each pipeline directory.

Compose services use `WAREHOUSE_HOST=postgis`, port `5432`, and the shared
database, user, and password settings. Layer loaders call
`src.shared.database.publish`: with a configured warehouse, publication
validates the GeoJSON and transactionally replaces the layer snapshot. Without
a warehouse password, local runs write GeoJSON under `DATA_DIR/layers/`.

Source files and caches are stored on the shared `etl/data/` mount. Schema
creation is handled by the warehouse's versioned migration runner, not by ETL
code.
