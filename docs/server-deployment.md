# Server deployment

GitHub Actions provides three manual workflows:

- `Deploy database` starts PostGIS if needed and applies pending migrations.
- `Deploy` deploys the backend and frontend in separate jobs.
- `Run ETL pipelines` runs a selected pipeline and stage.

The deployment jobs target a self-hosted Linux runner with Docker Compose, Python
3, and curl. The runner must have `self-hosted` and `linux` labels. Protect the
GitHub `production` environment with required reviewers.

## GitHub configuration

Set these secrets in the `production` environment:

| Secret | Used for |
| --- | --- |
| `WAREHOUSE_PASSWORD` | Connecting the backend, migration runner, and ETL to PostGIS |
| `MLAI_FRONTEND_GOONG` | Goong Map Tiles key embedded in the frontend build |
| `MLAI_BACKEND_GOONG` | Backend-only Goong REST credential |

Optional Actions variables are `WAREHOUSE_DATABASE`, `WAREHOUSE_USER`, and
`FRONTEND_PORT`. The defaults are `urbandynamics`, `urbandynamics`, and
`51873`. The frontend is the only service that publishes a host port. PostGIS,
backend, and ETL remain on the internal Compose network; backend health checks
run from inside its container.

The workflow generates a mode-restricted `.env` from the environment settings
and removes it after the job. Deployments are serialized on the runner. Do not
run another deployment from a separate checkout on the same host at the same
time.

## Trigger a workflow

```sh
gh workflow run deploy.yaml --repo RodrickSia/UrbanDynamics --ref main
gh run watch --repo RodrickSia/UrbanDynamics
```

Run `database-deploy.yaml` before deploying code that needs new migrations. The
ETL workflow requires PostGIS to be running and migrations already applied.

## Verify the frontend

The frontend job checks the page and Content Security Policy. To run the browser
deployment checks locally, set `DEPLOY_BASE_URL` to the frontend URL and run
from `frontend/`:

```sh
npx playwright test --config playwright.deploy.config.ts
```

This verifies browser map behavior in addition to HTTP availability. Keep all
backend-only credentials out of frontend build variables and source files.

The deploy job also runs `scripts/smoke_map_deployment.py` through the frontend
port. It requires backend health/readiness, API discovery, a loaded population
catalog, an HCMC population sample and a valid PNG tile. For each published map
vector layer it checks GeoJSON, TileJSON and the MVT endpoint (204 is a valid
empty tile). Unpublished layers are listed explicitly, not treated as loaded.
All probes are read-only. After opening a tunnel, the same check can run locally:

```sh
python scripts/smoke_map_deployment.py http://127.0.0.1:51873
```
