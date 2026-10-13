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

- [ ] Scenario metadata and independent deep clone. Verify lock, reorder, persistence, revision conflicts and immutable Existing (pytest).
- [ ] Authoritative selected-parcel geometry and persisted snapshots. Reject invalid/outside/unavailable parcel data (API tests).
- [ ] Pure building metrics, containment/overlap validation, template preview and parcel demolition commands. Confirm UNKNOWN vs proposed constraints, exact calculations (pytest).
- [ ] Development editor and scenario switching. Select/draw/edit/duplicate/delete/save, preview in 3D, retain failed drafts, restore overlays on style change (build, lint, browser).
- [ ] A/B metrics and provenance; no price-to-zoning inference. Verify same study area and baseline version (tests).
- [ ] Review and browser evidence; document live verification limits and deferred P1/P2.

## Research boundaries

Verified against [ArcGIS scenario documentation](https://doc.arcgis.com/en/urban/12.0/help/help-scenarios.htm) and [parcel development documentation](https://doc.arcgis.com/en/urban/12.0/help/help-parcel-redevelopment.htm). Scenario cloning, locking, metadata, parcel-based development and Ctrl snapping are documented. Strict version isolation, explicit draft confirmation, and UNKNOWN regulatory checks are UrbanDynamics choices. P1 stacking, basements, mixes, parcel subdivision, surfaces/envelopes and P2 split-view/export/history remain deferred per supplied specification.

## Live SSH smoke checklist

Use the existing user-managed tunnel (51873 frontend / 51874 API). No deployment is needed to inspect current data. After deployment is separately requested: select a real parcel in a plan, save a manual building in A, reload, clone B, change its height, verify A/Existing unchanged; demolish in B and restore; switch rapidly; change basemap/2D/3D; disconnect tunnel while saving and retry; verify locked writes and concurrent revision conflict. Compare selected polygon with source parcels and verify terrain anchoring visually. Baseline provider heights and geometry are not survey-verified.
