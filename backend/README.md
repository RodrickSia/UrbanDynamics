# Backend

The backend is a FastAPI service whose ASGI entry point is `app.main:app`.
Compose keeps it on the internal network; the frontend is the only service that
publishes a host port.

The API reads vector snapshots from the shared PostGIS layer tables. Configure
the warehouse with `WAREHOUSE_HOST`, `WAREHOUSE_PORT`, `WAREHOUSE_DATABASE`,
`WAREHOUSE_USER`, and `WAREHOUSE_PASSWORD`. In Compose, the host is `postgis` and
the port is `5432`. The backend does not create or migrate tables; use the
versioned migrations and runner in `infra/warehouse/`.

For API routes and frontend integration expectations, see
[`docs/khoi-implementation.md`](../docs/khoi-implementation.md) and
[`docs/frontend-backend-handoff.md`](../docs/frontend-backend-handoff.md).
