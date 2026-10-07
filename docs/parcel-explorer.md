# Parcel explorer

## Scope and acceptance

Repair repeated source-tile buffers, show land-use colors and stronger boundaries,
allow viewing from zoom 12, and open a centered parcel detail dialog using the
existing glass UI, GSAP and reduced-motion behavior. No ownership or planning
attributes are invented from the reference screenshot.

Build order: canonical geometry → vector styling/LOD → parcel detail and road-price
API → accessible detail dialog. Raw source fragments remain available for audit.

- A materialized, indexed parcel view unions fragments with the same source ID
  and administrative context once, outside interactive tile requests. Anonymous
  fragments remain separate. New ETL loads clip source buffers before insertion.
- The source sample's colors are presentation metadata, not a statutory palette.
  Missing/invalid land-use codes use a neutral color. A separate line layer draws
  boundaries with zoom-dependent widths.
- Zoom 12 is the initial overview limit. Sub-pixel plots are omitted at distant
  zooms; zooming in restores details. Native tiles stop at 16 and overzoom beyond
  that. Detail queries occur only on click, not on hover/pan or for every parcel.
- The new GET `/api/v1/parcels/{id}` returns source attributes, mapped area,
  planning breakdown and bounded nearby published road-price candidates. A
  unique nearby spatially checked road can provide an explicitly indicative
  unit price. Multiple nearby roads, unsupported land-use categories, unreviewed
  whole-road proxies or missing values must not produce an estimated total.
- Totals refer to mapped land area × land reference unit price, never house
  construction value, transaction price or cadastral valuation. Geometry area
  is labeled as calculated from the map. Matching method, distance, source and
  coverage qualifications are visible.
- Dialog: loading/error/retry, Escape, focus containment/restore, close button,
  narrow screens, no stale responses after another selection or layer disable.

## Verification

Python: `python -m pytest etl/tests/test_parcel_geometry.py backend/tests/test_parcels.py -q`.
PostGIS regression fixtures verify union areas and MVT features, query bounds,
neighbor selection and indexed spatial lookups in an isolated test database.
Frontend: `npm test`, `npm run build`, `npm run lint`; Playwright covers parcel
colors, borders, zoom 12/16, detail selection, dismissal and source cleanup.
Record benchmark measurements before settling the lowest usable zoom; do not
claim real production latency from fixture measurements.

Migration must run before the application deploy. Refresh the materialized view
after parcel ingestion, including a resumed load. Refresh preserves the old
published view until the replacement is ready. No raw records are deleted.
