# Architecture

The repository has four runtime components: frontend, backend, ETL jobs, and a
PostGIS warehouse. The frontend calls the backend. ETL jobs write snapshots to
the warehouse, and the backend reads those same snapshots for API responses.

```text
                      ┌──────────────┐
Browser ──HTTP───────>│   Frontend   │
                      └──────┬───────┘
                             │ internal Compose network
                      ┌──────▼───────┐       ┌──────────────┐
                      │   Backend    │──────>│   PostGIS    │
                      └──────────────┘       └──────▲───────┘
                                                   │
                                             ETL jobs
```

Compose publishes only the frontend. Backend, ETL, and PostGIS use the internal
Compose network; services connect to the database at `postgis:5432`.

PostGIS 17 stores relational data and population raster tiles. Flood and
land-price vector snapshots share `public.layer_snapshots` and
`public.layer_features`. Migrations under `infra/warehouse/migrations/` define
the schema and the warehouse runner records applied versions. ETL pipelines do
not create tables.

CI validates the database, backend, and frontend in independent jobs. Database
migrations deploy separately because they modify persistent data. Backend and
frontend deploy in separate jobs of the application workflow.
