# Development and scenarios — P0

## Gate audit (2026-10-13)

| Feature | Existing code / contract | Missing dependency / blocker | Priority |
|---|---|---|---|
| Plan persistence | `services/zoning/store.py`, `/api/v1/zoning/plans`, SQLite or PostgreSQL JSON documents; optimistic revision and transactions | No account/owner authorization exists; private workspace only | P0 reuse |
| Scenarios | `engine.py`, `useZoning.ts`, `ZoningWorkspace.tsx`; Existing locked; zone clone/lock/delete | Clone development, metadata, reorder, draft guards | P0 |
| Real parcels | `services/parcels.py`, `parcels.plot`, viewport MVT + price detail endpoint | Selected full geometry without price inference; immutable selected-parcel snapshot | P0 |
| Map editing | `ZoningScene.tsx`, MapLibre 6, geometry handles, snapping/Ctrl | Building tools and picking; reuse same map/editor | P0 |
| Baseline 3D | `layers/buildings3d.ts`: current checkout uses Goong VN_Building, not Overture | ID-aware demolition where supported; disclose unmaskable provider geometry/imagery | P0 |
| Terrain | `layers/terrain.ts`: Mapterhorn DEM, terrain-relative extrusions | No verified survey datum/heights; label approximate terrain anchor | P0 |
| Building simulation | `routers/building_scenarios.py`: standalone calculated scenarios | Not parcel-owned plan editor; keep separate | Reuse concepts only |
| Rules | Plan-local proposed types; no approved parcel rules | Never classify these as official allowed limits | P0 UNKNOWN |
| UI | Right white drawer, blue controls, compact scenario bar, GSAP | Preserve tokens, scrolling and keyboard behavior | P0 |
| Tests | pytest, Vitest, Playwright real backend/isolated SQLite | Live PostGIS/tunnel not available locally; require separate live smoke | P0 |

## Contract and design

Extend existing revision-checked commands, no new database or map instance. Persist selected full-resolution parcel snapshots and independent scenario buildings/masks in the plan document. IDs are strings. Clone uses new local IDs with origin lineage. Geometry/metrics use EPSG:32648, GeoJSON transport EPSG:4326. Simple above-ground massing uses a repeated floor plate and explicit floor count/height/use/GFA flags. All regulatory results remain UNKNOWN without a verified location-specific rule source; proposed zoning limits are evaluated separately as user assumptions.

Development panel job: select a real parcel, draw or preview a template, edit, validate, save. Primary action Save proposal. Explicit empty/loading/error/read-only/draft states. Existing sidebar colors, spacing, motion and responsive width. No generic cards or new animation framework. Draft survives validation/network errors; Save/Discard/Cancel before leaving it. No deployment in this task.

## Ordered work and acceptance

- [x] Scenario metadata and independent deep clone. Verify lock, reorder, persistence, revision conflicts and immutable Existing (pytest).
- [x] Selected-parcel source geometry and persisted snapshots. Reject invalid/outside/unavailable parcel data (API tests). Source cadastral accuracy remains unverified.
- [x] Pure building metrics, containment/overlap validation, template preview and parcel demolition commands. Confirm UNKNOWN vs proposed constraints, exact calculations (pytest).
- [x] Development editor and scenario switching. Select/draw/edit/duplicate/delete/save, preview in 3D, retain failed drafts, restore overlays on style change (build, lint, browser).
- [x] A/B metrics and provenance; no price-to-zoning inference. Verify same study area and baseline version (tests).
- [x] Review and browser evidence; document live verification limits and deferred P1/P2.

## Research boundaries

Verified against [ArcGIS scenario documentation](https://doc.arcgis.com/en/urban/12.0/help/help-scenarios.htm) and [parcel development documentation](https://doc.arcgis.com/en/urban/12.0/help/help-parcel-redevelopment.htm). Scenario cloning, locking, metadata, parcel-based development and Ctrl snapping are documented. Strict version isolation, explicit draft confirmation, and UNKNOWN regulatory checks are UrbanDynamics choices. P1 stacking, basements, mixes, parcel subdivision, surfaces/envelopes and P2 split-view/export/history remain deferred per supplied specification.

## Live SSH smoke checklist

Use the existing user-managed tunnel (51873 frontend / 51874 API). No deployment is needed to inspect current data. After deployment is separately requested: select a real parcel in a plan, save a manual building in A, reload, clone B, change its height, verify A/Existing unchanged; demolish in B and restore; switch rapidly; change basemap/2D/3D; disconnect tunnel while saving and retry; verify locked writes and concurrent revision conflict. Compare selected polygon with source parcels and verify terrain anchoring visually. Baseline provider heights and geometry are not survey-verified.

## Implemented contracts

- `GET /api/v1/zoning/plans/{id}/development/parcels/{parcel_id}?scenario_id=...` returns the saved full geometry snapshot, or reads that one source parcel; observed code, versioned starter catalog, proposal metrics and per-rule checks. First confirmed parcel mutation persists its snapshot. This does not claim a city-wide baseline capture at plan creation.
- Existing `POST /{id}/preview`: `save_building` validates a manual repeated floor plate, `generate_building` produces a conservative single low-rise footprint using explicit user assumptions and any more restrictive proposed zone limits. Neither writes storage.
- Existing `POST /{id}/commands`: `save_building`, `delete_building`, `demolish_parcel`, `restore_parcel`, `undo_development`, `redo_development`; all require current revision and an editable scenario. Geometry and resulting state commit atomically. No client-supplied parcel geometry is trusted.
- `add_scenario` deep-copies buildings, masks and applicable zoning types with fresh IDs/origin lineage. Type versions in the copy are independent. Equivalent copied types compare as unchanged zoning until their effective rules differ.
- Scenario metadata supports name, description, source selection, creation time, local-workspace creator, ordering, lock and deletion. Last active scenario is a local browser preference; saved geometry is backend-owned.
- Plan responses include per-scenario proposed GFA, FAR, coverage, space-use allocation, building count and demolition area. Existing GFA stays unknown; comparison uses the same study-area denominator and no percentage delta.

## Delivery matrix

| Verified ArcGIS concept | UrbanDynamics implementation | Deferred / assumption |
|---|---|---|
| Existing versus proposals; clone, name, description, order, lock | Persistent documents, revision checks, independent clone and immutable Existing | Existing map provider remains live; no complete historical city snapshot |
| Develop real selected parcels | MVT stable string ID → selected full geometry → frozen parcel snapshot | Positional/source accuracy not survey-verified |
| Draw and edit building spaces | One repeated footprint, vertex handles, floors/height/use, GFA/FAR flags, duplicate/delete, preview/save, saved undo/redo | Stacked parts, distinct per-floor uses, underground, elevation gizmos and full transform are P1 |
| Assign building types | Immutable versioned low-rise template plus four space-use presets; explicit coverage/setback/floor assumptions | Catalog CRUD, mixes and density generation are P1 |
| Validate versus rules | Geometry/overlap errors block save; official rules UNKNOWN; proposed limits PASS/FAIL separately | No official rule importer or verified frontage; no legal approval claim |
| Demolish per scenario | Persisted parcel masks; provider IDs suppress intersecting extrusions; contained anonymous extrusions suppressed spatially; original filters restored | Partly intersecting anonymous geometry, imagery, and unavailable tree layers cannot reliably be suppressed |
| Scenario comparison | A/B toggle and numeric cards/table, proposal-only metrics, explicit units | Split view, analytics, export/publish, history are P2 |

## Verification and operational limits

- `pytest backend/tests/test_development.py backend/tests/test_zoning.py backend/tests/test_parcels.py`: 58 passed; the existing isolated-PostGIS integration test is skipped because no test database is configured.
- Frontend production build and ESLint pass; Vitest: 122 tests pass.
- Existing real-API zoning browser suite: 3 pass, including split/merge/undo, style reload and measurement ownership.
- Development browser suite: 1 complete end-to-end test passes (manual draw/save, failed-save draft retention, clone/edit/lock, overlap rejection, discard, masks, style restore, reload, comparison and low-rise template preview/save). It uses the real FastAPI command/store engine, isolated SQLite and a deterministic selected-parcel provider fixture (`backend/tests/development_testserver.py`). It is not evidence of live warehouse geometry correctness.
- Browser evidence: `.runtime/development/massing-3d.png`, `comparison.png`, `sidebar-1440.png`, `sidebar-320.png`. Responsive overflow checked at 320/768/1024/1440.
- Live probe `http://127.0.0.1:51874/health` returned connection reset on 2026-10-13. Live PostGIS, source accuracy and server-156 smoke verification remain unconfirmed. No deploy performed.
- Authentication is unchanged: this is the existing private workspace API, not a new multi-user authorization system. Baseline metrics/heights and terrain datum remain unknown/unverified where sources cannot establish them.

To reproduce browser checks, start `uvicorn development_testserver:app --host 127.0.0.1 --port 8087` with `PYTHONPATH=backend;etl;backend/tests` and an isolated `ZONING_DATA_DIR`; run Vite 5178 with `API_PROXY_TARGET=http://127.0.0.1:8087`, then `npx playwright test --config playwright.development.config.ts`. Never use the fixture server for production.
