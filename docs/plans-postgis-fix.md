# Plans HTTP 422 — psycopg batch execution

The backend called `Connection.executemany()` in seven projection/catalog paths. psycopg 3.3.6 exposes it on a cursor; the resulting `AttributeError` was masked by the zoning router as HTTP 422, “Invalid zoning command or geometry”.

All seven paths now call a common helper that opens/closes a cursor and executes the batch inside the caller's existing transaction. The helper does not commit independently, preserving atomic document/projection updates.

Verification on 16 October 2026:

- 102 tests passed, including real PostGIS projection of catalog/types/scenarios/zones/buildings/parcels/masks and API create/list/open/update/delete.
- PostGIS tests run on a disposable private database, not the team warehouse. The harness now provides `TEST_DATABASE_URL` and bundles the zoning catalog needed by the projection tests.
- A rollback-only probe on server 156 confirmed successful schema initialization/backfill for the existing source document (1 source plan, 1 projected plan). No source document was changed by the probe.
- Existing client input validation and the current plan/scenario model are unchanged.
