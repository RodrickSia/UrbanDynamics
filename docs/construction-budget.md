# Plan construction budgets

Open a plan, select its scenario, then Dashboard → the money icon. This view estimates construction spending, not market property value or land acquisition cost. Existing is retained and has no new-work bill.

## Calculation and assumptions

- Physical floor area = metric footprint × number of floors. Floors excluded from regulatory GFA/FAR still cost money to build. A per-building contract floor-area override is available.
- Converted area = physical floors + footprint × foundation factor + footprint × roof factor + additional item areas × their factors.
- Construction = converted area × unit price × location × access × complexity.
- Subtotal = construction + demolition + shared extras not included in the quote.
- Total = subtotal × (1 + VAT if excluded) × (1 + contingency).
- VND amounts round to whole dong. Independently rounded building totals can differ from the scenario total by a few dong. Shared extras and demolition are shown separately and counted once.

Initial **user-supplied** HCMC townhouse rates: shell/finishing labor 3,600,000; standard turnkey 5,300,000; mid-range turnkey 6,000,000 VND/m². Premium/custom require a quote. All rates and factors can be changed and sources retained. Initial foundation 0.5 and roof 0.4 represent a strip foundation and concrete roof assumption; use zero for absent components. Location/access/complexity start at 1; VAT/contingency at 0, not an assertion about applicable tax. Extra areas require explicit confirmation that they do not overlap counted floors, foundation or roof. Basement, balcony and terrace areas can be entered individually with their contract coefficients.

Settings apply to the scenario with optional building-specific profiles. Piling, design, permits and special works are shared amounts; an included flag prevents charging them twice. This is a configurable m² estimate, not an automated bill-of-quantities/material takeoff. High-rise and non-residential buildings need project-specific quotes.

## Demolition data

Saved demolition masks are land extents, never assumed to be building floor area. Their union queries the generated baseline inventory once; duplicate footprints are removed. Only intersecting footprint area × baseline floors is counted. Generated footprints/floors are estimates and partial demolition needs a surveyed quote. Goong visual meshes are not an authoritative demolition inventory.

Demolition area defaults to **Automatic**. Recorded floors take priority; if absent, positive building height is divided by an editable assumed floor height (initially 3.2 m), rounded to the nearest whole floor (minimum one). Each row exposes footprint, floor count and whether height estimation was used. Width alone is insufficient: mapped footprint geometry supplies actual floor-plate area. Missing inventory, unrepresented masks or missing both height and floors keep the total **incomplete**.

The automatic demolition unit rate is **200,000 VND/m² of floor area**, an app budgeting assumption, not a verified contractor quote. `demolition_rate: null` selects this default, including previously saved nulls; explicit rates (including zero) are preserved. Users can edit the rate or reset it to Automatic, configure assumed floor height, choose a custom total floor area, or mark demolition already included in construction. Settings persist per scenario through the existing revision-aware command. Saving recalculates from current demolition masks; restoring a parcel removes its demolition charge. No demolition masks means no charge.

The costs API includes `demolition_default_rate`, effective `demolition_rate`, and aggregate `demolition_area_m2` (null when incomplete or included). The assumptions form and each demolition row show the calculation basis. Existing Goong-only buildings still require a manual area when no corresponding server inventory is available.

## Storage/API

- `GET /api/v1/zoning/plans/{id}/costs?scenario_id=…&revision=…` computes from the server-side plan. A stale revision returns 409.
- The existing revision-aware commands API accepts `save_cost_settings`. It validates finite non-negative values, scenario ownership of building overrides and locks/reference immutability.
- `scenario.cost_settings` persists in the existing authoritative plan document (PostgreSQL or local SQLite). No schema migration is needed. Scenario duplication remaps building override IDs. Deleted building overrides are omitted from the editable report; retained document entries allow development undo to restore their quote before the next budget save.
- Read errors and save failures are visible with retry; API data has no dependencies on external price services.

## Reference context

The supplied market ranges can be compared with [Kim Anh's published construction pricing](https://www.xaydungkimanh.com/chi-phi-xay-nha-tron-goi.html). They are indicative quotes, not a regulated price schedule. [Circular 37/2026/TT-BXD](https://chinhphu.vn/?docid=218630&pageid=27160&typegroupid=6), effective 1 July 2026, concerns methods for norms and materials/labor/machinery pricing; it does not establish these app presets.

## Verification

`python -m pytest backend/tests/test_construction_costs.py` covers physical vs regulatory area, arithmetic, overlapping demolition masks, unknown data, persistence, revisions, locks and cloned profiles. Browser coverage in `frontend/tests/browser/construction-costs.spec.ts` exercises Dashboard navigation, profile editing, errors and responsive layout against a deterministic API fixture. Live server building coverage and surveyed rates remain deployment-specific.
