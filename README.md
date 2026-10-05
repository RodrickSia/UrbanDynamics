# UrbanDynamics

UrbanDynamics is organized as a monorepo with separate frontend, backend, and ETL services.

## Services

- `frontend/` contains the web client. The initial scaffold serves a placeholder page; choose the application framework when the UI work begins.
- `backend/` contains the FastAPI application and APIs used by the frontend.
- `etl/` contains the data pipelines that load source data into the warehouse.
- `infra/warehouse/` contains the PostGIS image, initialization scripts, and versioned SQL migrations.

## Local development

Copy `.env.example` to `.env`, then start the services with `docker compose up --build`. Run ETL pipelines explicitly with their Compose profiles.

See [docs/architecture.md](docs/architecture.md) for the initial service boundaries and [docs/development.md](docs/development.md) for repository conventions.

## CI/CD

GitHub Actions CI builds and validates the database, backend, and frontend independently. Application deployment updates the backend and frontend together; database migrations use a separate manual workflow against the running PostGIS service. Configure the GitHub `production` environment with required reviewers and a `WAREHOUSE_PASSWORD` secret before using either deployment workflow.
