# Zoning plan editor — first milestone

Implements the supplied [business specification](zoning-business-specification.md)'s 2D MVP.
Plans and Indicators are icon buttons below search; scenario tabs use the existing
glass surface, teal tokens and reduced-motion-aware animation. No Projects entry.
The Plans workspace opens as a full-height left sidebar. Saved plans can be deleted
after confirmation; deletion requires the current revision and removes the whole
plan document, including scenarios.

## Delivery and contract

1. Plan API and durable persistence: fixed-version empty/unverified Existing
   snapshot, independent alternatives, plan-scoped proposal types, revision checks.
2. Geometry operations: draw/reshape, explicit preserve/replace preview, split,
   merge, delete, study-area clipping, validation and bounded undo/redo history.
3. Map editor and inspector: exclusive pointer ownership, editable vertices,
   legend, scenario management, loading/error/empty states and durable saves.
4. Indicators: assigned/unassigned/changed area, category comparison and optional
   independent FAR/coverage bounds; missing controls remain Unknown.

GeoJSON is WGS84; topology and areas use UTM 48N (EPSG:32648). The first release
accepts small HCMC-area studies (10 m²–25 km²), at most 500 zones and 2,000 vertices
per input geometry. No automatic conversion from parcel use or prices into zoning.
Reference geometry is empty until an authoritative import workflow exists; its
snapshot records that explicitly. Proposed numeric controls never imply approval.
During study-area and zoning drawing, vertices and edges snap within 10 screen pixels
to visible parcel outlines, zoning geometry, and road/water vector features exposed
by the active basemap. Holding Ctrl temporarily disables snapping. Road polygons
are used only when supplied by a vector layer; the repository does not contain an
authoritative right-of-way polygon dataset. Satellite imagery alone supplies no
road or water vectors.

The optional Show parcel outlines control draws no parcel fill or parcel detail UI.
After a plan is created, `/api/v1/zoning/plans/{id}/parcels/tiles/{z}/{x}/{y}.pbf`
clips parcel geometry against its saved study area in PostGIS before vector-tile
encoding. Outside parcels and ordinary parcel overlays are hidden in the zoning
workspace. Plan parcel tiles require the parcel warehouse; local SQLite-only
development shows no parcel outlines.

Production storage uses the existing PostgreSQL connection and a separate JSONB
plan table. Local development uses transactional SQLite under DATA_DIR (or
ZONING_DATA_DIR). Updates are atomic and require the revision read by the client;
stale updates return 409. The current application is a shared trusted workspace;
team identity/permissions and public sharing require a later authenticated release.

## Verification

- Backend pytest: persistence, stale writes, reference immutability, independent
  scenarios, invalid geometry, deterministic overlaps, split/merge, area metrics,
  undo/redo, unknown values and locks.
- Frontend build/lint and editor tests; browser exercise with deterministic map
  fixtures and real local API for create/edit/reload, style changes and tool isolation.
- Preserve existing measurement, viewshed, parcels and land-price behavior.

Phase 2 parcel painting (requires verified geometry), overlays, parcel exceptions,
and sourced compatibility checks remain separate. Phase 3 envelopes require
verified height/setback/terrain inputs. They are not represented as completed tools.

References: [zoning](https://doc.esri.com/en/arcgis-urban/latest/help/help-zoning.html)
and [scenarios](https://doc.esri.com/en/arcgis-urban/latest/help/help-scenarios.html).

## Run and verify

Start the API with the repository's Python dependencies installed and `backend`
and `etl` on `PYTHONPATH`: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8087`.
For isolated browser verification set `ZONING_DATA_DIR` to a disposable local
directory and leave warehouse credentials unset. This exercises SQLite; production
uses PostgreSQL automatically when the warehouse connection is configured.

From `frontend` run:

```text
npm run build
npm run lint
npm test -- --maxWorkers=2
npx playwright test --config playwright.zoning.config.ts
```

The zoning browser config uses port 5178 and proxies to the local API on 8087.
It mocks only the basemap/dataset context; plan create/read/write calls use the real
API. Its tests live outside the regular map fixture suite, which needs no backend.
Backend: `python -m pytest backend/tests/test_zoning.py backend/tests/test_map_api.py -q`.

## User workflow

Plans → New plan → draw study area → Create plan → Add zoning type → Draw zone →
Preview → Confirm zoning. Overlap handling is selected explicitly before preview.
Select a zone for its regulations, assignment, delete or vertex editing. Drag a
vertex; click a midpoint to insert; Shift-click a vertex to remove. Shift-click
multiple zones of the same type to merge; draw a crossing line to split. Undo/redo
applies to geometry changes in the current unlocked proposal scenario.

The plus beside the scenario tabs duplicates the active scenario. Options rename,
lock/unlock or delete proposals. Indicators compares areas against another scenario,
shows unknown source controls and independent FAR/coverage bounds. The panel can be
collapsed while drawing. Confirmed changes save immediately to the backend.
