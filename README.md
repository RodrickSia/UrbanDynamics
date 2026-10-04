# UrbanDynamics

UrbanDynamics is organized as a monorepo with separate frontend, backend, and ETL services.

## Services

- `frontend/` contains the web client. The initial scaffold serves a placeholder page; choose the application framework when the UI work begins.
- `backend/` contains the FastAPI application and APIs used by the frontend.
- `etl/` contains the pipeline entry point, implemented flood/land-price pipelines and the rainfall/population scaffolds. Scheduled execution is still pending.
- `infra/warehouse/` contains the PostGIS layer schema migration.

## Local development

Copy `.env.example` to `.env`, then start the services with `docker compose up --build`. ETL services are opt-in: `docker compose --profile etl-population-hcmc run --rm etl-population-hcmc` or `docker compose --profile etl-rainwater run --rm etl-rainwater`.

See [docs/architecture.md](docs/architecture.md) for the initial service boundaries and [docs/development.md](docs/development.md) for repository conventions.

Khôi's flood and land-price implementation has a separate local PostGIS stack. See [the implementation guide](docs/khoi-implementation.md) and [local test report](docs/khoi-local-test-report.md). Run `.venv/Scripts/python.exe scripts/test-khoi-local.py`; API documentation is served at `http://127.0.0.1:8001/docs`.

## CI/CD

GitHub Actions workflows belong in `.github/workflows/`. Workflows that deploy should target the configured self-hosted runner using repository or environment secrets; do not commit credentials or runner-specific configuration.
