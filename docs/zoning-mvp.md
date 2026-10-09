# Zoning plan editor — first milestone

Implements the supplied ArcGIS Urban–inspired business specification's 2D MVP.
Plans and Indicators are icon buttons below search; scenario tabs use the existing
glass surface, teal tokens and reduced-motion-aware animation. No Projects entry.

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
