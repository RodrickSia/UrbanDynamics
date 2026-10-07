# UrbanDynamics

UrbanDynamics is organized as a monorepo with separate frontend, backend, and ETL services.

## Services

- `frontend/` contains the web client. The initial scaffold serves a placeholder page; choose the application framework when the UI work begins.
- `backend/` contains the FastAPI application and APIs used by the frontend.
- `etl/` contains flood, land-price and rainfall pipelines, plus Khôi's persistent ETL service. Population remains a scaffold.
- `infra/warehouse/` contains the PostGIS layer schema migration.

## Local development

Copy `.env.example` to `.env`, then start the services with `docker compose up --build`. ETL services are opt-in: `docker compose --profile etl-population-hcmc run --rm etl-population-hcmc` or `docker compose --profile etl-rainwater up -d etl-rainwater` for continuous rainfall updates.

See [docs/architecture.md](docs/architecture.md) for the initial service boundaries and [docs/development.md](docs/development.md) for repository conventions.

Khôi's flood and land-price implementation has a separate local PostGIS stack. See [the implementation guide](docs/khoi-implementation.md) and [local test report](docs/khoi-local-test-report.md). Run `.venv/Scripts/python.exe scripts/test-khoi-local.py`; API documentation is served at `http://127.0.0.1:8001/docs`.

For the expanded HCMC scope (including former Bình Dương, Bà Rịa–Vũng Tàu and Côn Đảo), rainfall ownership and continuous updates, use [Khôi's citywide ETL guide](docs/khoi-citywide-etl.md).

Building-impact screening has a standalone demo at `http://127.0.0.1:8001/simulation`: enter the existing site and proposed building, predict runoff/land-cover and traffic/utility demand, assess impacts against stated targets/capacity, then request generated improvements within a budget and constraints. No improved design is required as input. Save/reopen results and export JSON or print a report. See [the current simulation guide](docs/building-impact-prediction.md): forecasts use planner-supplied factors; hydraulic flood depth, traffic queues/travel time and thermal simulation are not implemented.

## CI/CD

Integrated building simulation is available at `http://127.0.0.1:8001/simulation/integrated`, starting with a residential building in Thu Duc. It runs real SUMO/SWMM on explicitly synthetic networks, geometric shadows, shared hourly demand and multi-feature recommendations. See [implementation and limits](docs/integrated-building-impact.md) and [deployment preparation for 156](docs/integrated-deployment.md). AI explanation is deferred; advanced thermal/2D/water-pressure solvers remain unavailable.

For the current demo inventory, data limits and prioritized feature plan, see [demo status and feature roadmap](docs/demo-status-and-feature-roadmap.md) (Vietnamese, updated 06/10/2026).

GitHub Actions workflows belong in `.github/workflows/`. Workflows that deploy should target the configured self-hosted runner using repository or environment secrets; do not commit credentials or runner-specific configuration.
