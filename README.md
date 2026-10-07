# UrbanDynamics

UrbanDynamics is a monorepo for an urban map application and its data pipelines.

## Services

- `frontend/`: React, TypeScript, Vite, and MapLibre map workspace.
- `backend/`: FastAPI API used by the frontend; reads shared layers from PostGIS.
- `etl/`: population, flood, and land-price pipeline code. Flood-risk uses
  rainfall forecast and history files as inputs.
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

- [Integrated building simulation: SUMO/SWMM, hourly demand, shadows and rerun recommendations](docs/integrated-building-impact.md)
- [Citywide rainfall/flood/land-price ETL and scheduler](docs/khoi-citywide-etl.md)
- [Combined local regression report](docs/integrated-simulation-test-report.md)
- [Integrated deployment preparation for 156](docs/integrated-deployment.md)

The shared application retains `compose.yaml`, PostGIS 17 and the team's frontend.
For isolated simulation development, `compose.khoi.yaml` exposes the demo at
`http://127.0.0.1:8001/simulation/integrated`. It starts with a residential building
in Thu Duc and runs native SUMO/SWMM on explicitly synthetic networks. AI
explanation is deferred; advanced thermal/2D/water-pressure solvers are pending.

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
