# UrbanDynamics

UrbanDynamics is organized as a monorepo with separate frontend, backend, and ETL services.

## Services

- `frontend/` contains the React/TypeScript urban map workspace built with Vite, MapLibre GL JS, and Goong Map Tiles.
- `backend/` contains the FastAPI application and APIs used by the frontend.
- `etl/` contains the hourly data pipeline entry point. Its implementation and scheduler are intentionally undecided.
- `infra/warehouse/` is reserved for warehouse schema and migrations once the warehouse technology is selected.

## Local development

Copy `.env.example` to `.env`, then start the services with `docker compose up --build`. The ETL container is opt-in with the `etl` Compose profile: `docker compose --profile etl run --rm etl`.

See [docs/architecture.md](docs/architecture.md) for the initial service boundaries and [docs/development.md](docs/development.md) for repository conventions.

## CI/CD

GitHub Actions workflows belong in `.github/workflows/`. Workflows that deploy should target the configured self-hosted runner using repository or environment secrets; do not commit credentials or runner-specific configuration.
