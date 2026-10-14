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
  is labeled as mapped area. Matching method, distance, source and
  coverage qualifications are visible.
- Dialog: loading/error/retry, Escape, focus containment/restore, close button,
  narrow screens, no stale responses after another selection or layer disable.

## Verification

The observed MDSDD labels are classified conservatively in
`backend/app/services/parcel_classification.py`. ODT and OTC are the only
confident residential codes. Clear retail/hospitality/fuel-service codes map
to Commercial; clear institutional/utility/industrial codes map to Other
non-agricultural. Ambiguous values remain unmapped with `null` unit and total
prices. Rates come from the matched road feature's category column, not global
example rates. Planning-area breakdowns do not prove current cadastral mixed
use, so they are displayed without contributing to parcel value. The result
retains the source code, normalized family, category, road match and geometry
review status, confidence, and price provenance.

### Citywide automatic road references

The citywide publication uses `match_confidence=automatic_reference`,
`publication_match_mode=automatic`, `price_kind=table_reference` and coverage
`citywide_road_reference` or `actual_road_piece_reference`. These fields must
survive the detail API's public metadata filter. Otherwise valid published
prices are rejected as unverified even when a road is found next to the parcel.
These references now provide the matching land-use category's unit price with
low confidence, without an estimated total. Ward allocations may borrow another
road's table row; the UI retains `source_road` and distinguishes these allocations
from direct road-name matches. Existing distance, ambiguity and land-use checks
still apply. Missing prices remain null; citywide publication is not proof of
verified parcel frontage.

On 2026-10-14 the running API returned `unverified` for parcels 1568422 and
1568426 despite a Trần Quốc Thảo candidate at 8.69 m and 22.27 m respectively.
Regression fixtures use that published rate triple (210,600,000 residential,
147,400,000 commercial, 126,400,000 other non-agricultural VND/m²). Tests cover
the metadata filter through the API and the resulting unit-price dialog.

Python: `python -m pytest etl/tests/test_parcel_geometry.py backend/tests/test_parcels.py -q`.
PostGIS regression fixtures verify union areas, normalized land-use colors, MVT
features at zoom 12/14/16 and road-price association in an isolated test database.
Frontend: `npm test`, `npm run build`, `npm run lint`; Playwright covers parcel
colors, borders, zoom 12/16, detail selection, dismissal and source cleanup.
Record benchmark measurements before settling the lowest usable zoom; do not
claim real production latency from fixture measurements.

Migration must run before the application deploy. Refresh the materialized view
after parcel ingestion, including a resumed load. Refresh preserves the old
published view until the replacement is ready. No raw records are deleted.
