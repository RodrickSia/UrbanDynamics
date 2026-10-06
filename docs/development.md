# Development

## Local services

Use the root `compose.yaml` for the application and warehouse. Copy
`.env.example` to `.env`, set a unique `WAREHOUSE_PASSWORD` before initializing
PostGIS, then start the desired services. Only the frontend publishes a host
port; backend, PostGIS, and ETL communicate over the Compose network.

ETL pipelines are opt-in profiles. Choose a profile and service from
[`etl/README.md`](../etl/README.md). Keep source data, caches, and generated
results under the ignored `etl/data/` directory.

## Repository conventions

- Keep pipeline-specific sources, models, transformations, and loading code in
  that pipeline's directory. Put shared infrastructure in `etl/src/shared/`.
- Keep schema changes in numbered SQL migrations under
  `infra/warehouse/migrations/`; use the shared migration runner.
- Keep service dependencies and Docker build contexts scoped to the service.
- Store credentials in an untracked `.env` or GitHub Actions environment
  secrets. Commit only variable names and safe local defaults in
  `.env.example`.
- Put automation in `.github/workflows/`. Keep deployment credentials and
  self-hosted runner labels in GitHub environment configuration.

## CI and deployment

CI runs on pushes and pull requests. `integration-tests.yaml` exercises the
flood, land-price, and API integration against an isolated database. Use the
manual `Deploy database` workflow for migrations and `Deploy` for the
application. `Run ETL pipelines` provides pipeline and stage choices for
manual ETL runs, including standalone transform and load stages for parcels.
