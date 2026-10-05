# UrbanDynamics

UrbanDynamics is a monorepo for an urban map application and its data pipelines.

## Services

- `frontend/`: React, TypeScript, Vite, and MapLibre map workspace.
- `backend/`: FastAPI API used by the frontend; reads shared layers from PostGIS.
- `etl/`: population, flood, rainwater, and land-price pipeline code.
- `infra/warehouse/`: PostGIS 17 image, initialization, and versioned migrations.
- `compose.yaml`: local services and one opt-in Compose profile per ETL pipeline.

## Local setup

Copy `.env.example` to `.env`, set a unique `WAREHOUSE_PASSWORD`, and set the
frontend Goong Map Tiles key if you want to render the map. Start the application
and warehouse with:

```sh
docker compose up --build
```

Only the frontend publishes a host port. Backend, PostGIS, and ETL communicate
over the Compose network; the database hostname is `postgis` on port `5432`.
See [ETL usage](etl/README.md) to run a pipeline and
[warehouse operations](infra/warehouse/README.md) for migrations.

## Documentation

- [Architecture](docs/architecture.md)
- [Development](docs/development.md)
- [Flood and land-price ETL guide](docs/khoi-implementation.md)
- [Frontend/backend API handoff](docs/frontend-backend-handoff.md)
- [Historical local integration test report](docs/khoi-local-test-report.md)

## GitHub Actions

- `CI` validates the database, backend, and frontend.
- `Integration tests` runs flood, land-price, and API checks against an isolated
  PostGIS database.
- `Run ETL pipelines` is manually triggered and lets you choose a pipeline and
  either the full pipeline or extraction stage.
- `Deploy database` applies pending migrations. `Deploy` updates backend and
  frontend in separate jobs.

Deployment workflows use the protected `production` environment. Configure its
`WAREHOUSE_PASSWORD` secret to match the production database.
