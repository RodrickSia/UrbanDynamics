# UrbanDynamics — ArcGIS Urban–inspired Plan / Zoning Business Specification

**Scope:** Describe business requirements, expected behavior, input data, rules, UI, and phased delivery of a Zoning Plan feature. **No implementation code.**

**Target area:** Start with a small, data-verified study area in Thủ Đức (within HCMC), then expand to other areas of HCMC. This document is a product design proposal informed by Esri's ArcGIS Urban documentation, **not** a claim of equivalence to ArcGIS Urban or a legal determination of allowable development in HCMC.

## 1. What Zoning does

A Zoning Plan lets an urban planner create **alternative spatial regulations** for a study area, apply those regulations to geographic zones/parcels, inspect effective controls, detect inconsistencies, and compare scenarios. It answers:

- **Where?** Which geographic area or parcel is subject to a rule?
- **What use?** What land/building functions are allowed, conditionally allowed, or restricted?
- **How much?** What maximum height, number of floors, coverage, floor-area ratio (FAR), dwelling-unit density, and setbacks apply?
- **What changes?** How does a proposed scenario differ from existing/reference planning?
- **What impact?** How much land changes zoning, what potential development capacity exists, and which conflicts require review?

**Key distinction:** A zoning plan is not just a color-coded land-use map; it is a versioned scenario containing **rules + polygons + actions + metrics + provenance**.

## 2. Core business entities

### 2.1 Plan

One planning workspace covering a fixed *study area* polygon. Proposed fields: plan ID; name; study-area geometry; author/team; description; source baseline; jurisdiction; plan status (draft/reviewed); created/modified timestamps; source document links; plan permissions. A plan may have multiple scenarios.

Creation: select parcels; draw a study-area polygon; import a GIS polygon; or create from a geocoded address. Study area should be editable with explicit validation.

### 2.2 Scenario

A *scenario* is a specific design alternative within one plan:

- **Existing / Reference** — a read-only snapshot of the best available current/reference information, with sources and uncertainty identified.
- **Scenario A** — an editable alternative.
- **Scenario B** — another independently editable alternative, usually duplicated from A or Existing.

Users can create, duplicate, rename, select, lock, compare, and delete scenarios (subject to permissions); copying a scenario must not alter the reference snapshot. A proposed scenario **never modifies official regulations or authoritative data**. Store the exact baseline version used.

### 2.3 Zoning type

A **non-spatial rule template** (does not itself have geometry):

- Identifiers: `zone_type_id`, code, human-readable name, description.
- Visual identity: map color, polygon fill and outline, legend order.
- Uses: allowed, conditionally allowed, prohibited space-use categories when supported by actual rule sources.
- Basic restrictions: max floors, max height (m), maximum coverage (%), max FAR, maximum underground depth (if supported), permitted dwelling-unit density (when applicable).
- Advanced restrictions: setbacks (front/side/rear or by street-facing edges), tiered setbacks, optional skyplanes.
- Governance: source type, legal/document reference, date of validity, verification status, version, and whether it is **official/reference** or **scenario proposal**.

A type may apply to many geographically separate zoning boundaries.

### 2.4 Zoning boundary

A polygon referencing a zoning type. Contains geometry, scenario, zone-type ID, source/approval provenance, and revision metadata. In **one proposed base-zoning scenario**, areas of different base zones must not overlap in a way that assigns contradictory base types to the same location. Boundary-edit rules must be explicit (replace/clip/merge). Gaps should be shown as unassigned rather than silently filled.

### 2.5 Parcel

A physical/cadastral parcel polygon, *separate* from zoning boundaries. A zone can span many parcels; a parcel can intersect more than one zone. A parcel's cadastral land-use code, official detailed-planning designation, and UrbanDynamics scenario zone are **not automatically interchangeable**. Preserve original codes and data provenance.

### 2.6 Zoning overlay

A polygon defining additional rules over base zoning, for example a hypothetical conservation restriction, height-control corridor, or flood-prone development constraint. Its type specifies *how* it combines with the base control: replace a restriction, impose a stricter cap, or apply a clearly defined bonus. Two overlays may overlap; their conflict/priority order must be controlled. **An environmental layer does not automatically have legal regulatory force**: label research/advisory overlays separately from official zoning controls.

### 2.7 Parcel override

A specific exception applied to one parcel in a proposed scenario. It overrides defined base zoning/overlay attributes **only within that scenario**, with an explanation, provenance, permission/audit trail, and an obvious badge in the inspector. It must not silently edit the underlying zone type or official reference data.

### 2.8 Validation finding

A computed or manually reviewed warning. Properties: affected feature IDs, rule or compatibility matrix involved, observed and permitted values, severity (info/warning/blocker), data sources, and whether validation was *definitive*, *provisional*, or *unknown due to missing data*.

## 3. Main end-user workflow

1. **Create Plan:** select study area in Thủ Đức; choose reference datasets and planning horizon; name and save plan.
2. **Inspect Existing:** display known parcel, zoning, existing-building and planning layers; visually distinguish official/reference from inferred/unverified data.
3. **Create Scenario A:** clone baseline; begin editing only the scenario copy.
4. **Choose a Zoning Type:** pick a predefined type or add/edit a plan-specific type and its regulations.
5. **Assign geographic area:** draw a zoning polygon or paint selected parcel(s); preview and confirm overlap behavior.
6. **Edit geometry:** move vertices, snap to parcels, split, merge, reshape, erase; undo/redo.
7. **Inspect zone or parcel:** see active zoning type, constraints, area, effective overrides, provenance, and conflicts.
8. **Validate:** check invalid geometry, unassigned areas, conflicts, inconsistent land-use compatibility, and missing required rule metadata.
9. **Compare:** duplicate Scenario A into B; modify zoning; compare changed areas, category distribution and development-potential estimates when defensible.
10. **Save & share:** persist plan and scenarios, with a draft/proposal label and a readable summary.

## 4. Zoning toolset and required behavior

### 4.1 Zoning types management

- List types with legend colors, labels and concise regulation summary.
- Search/filter by code, name or category.
- Add a new type (code, name, color, restrictions); duplicate a type; edit; archive/delete if unused; reorder legend.
- Editing a plan type updates areas referencing it **within the current plan**; show confirmation when change affects multiple scenarios.
- Import types from a structured dataset in a later phase only; reject ambiguous/invalid rows with a review report.

### 4.2 Boundary creation/editing

- **Draw polygon:** select type → draw map polygon → snap → preview affected zones → confirm. Enforce validity, closed rings and appropriate projection/area handling.
- **Paint parcels:** select type → click/brush one or more cadastral parcels. Only available when a trusted parcel boundary layer exists. Support multi-select and visible brush feedback.
- **Change assignment:** click zone → select a different type; optional merge with neighboring same-type zones.
- **Split:** user draws cut line across zone; both parts retain the original type unless changed afterward.
- **Merge:** union adjacent same-type regions (subject to geometry validity), preserving provenance/revision data.
- **Reshape:** move/add/delete boundary vertices with snapping and undo/redo.
- **Delete:** remove only the selected scenario boundary; ask for confirmation on destructive actions.
- **Copy to scenario:** support preserve existing boundaries (clip incoming) or replace areas under incoming geometry (clip existing); show preview.
- On overlap, apply an explicit geometric **clip/replace** policy. Do **not** silently stack competing base zones.

### 4.3 Zoning overlay types + boundaries (phase 2)

- Add overlay category (visual grouping + interaction policy).
- Draw/paint overlay polygon, potentially crossing multiple base zone polygons.
- Define specific override rules on the **overlay boundary**; specify conflict priority.
- Example *illustrative only*: conservation overlay sets max height to a stricter value. This is not a legal HCMC restriction unless an actual document supports it.
- Inspect resulting **effective** parameters and which rule produced each one.

### 4.4 Parcel-level overrides (phase 2)

- Select parcel, inspect inherited type and overlay controls.
- Propose an exception for only that parcel (e.g. a revised maximum height in Scenario B).
- Show original value, proposed value, explanation and reviewer; allow reset to inherited value.
- Use a visible badge: `Scenario override — not an official approval`.

### 4.5 Scenario management

- Existing is read-only, alternatives editable.
- Copy/rename/lock scenarios; preserve independent geometry states; no cross-scenario accidental mutation.
- Switch scenarios without losing map camera, selection or inspector unnecessarily.
- Compare zone area and label changes between scenarios; optionally side-by-side or swipe comparison later.
- Manage branch-like draft/review status but do not imply legal permit/approval.

### 4.6 Inspect / explanation

On clicking a zone or parcel, show:

- Location, polygon area and selected zone code/name.
- Intended/allowed uses, max height, floors, coverage, FAR; setbacks only when specified.
- `Effective rules` derived from base zone + overlays + parcel override, including an explanation of precedence.
- Current reference value vs scenario-proposed value.
- Source, issuing body, decision/document, approval/effective date, reviewed/unverified status, update timestamp.
- Related parcels, conflicts and missing-input warnings.

Use `Unknown/not available` rather than a zero or fabricated regulation when a field is absent.

### 4.7 Validation

- Polygon self-intersections, invalid rings, slivers, duplicates and holes.
- Overlaps between contradictory base-zoning boundaries and gaps within intended coverage.
- Zone assignment missing/invalid type references.
- Parcels spanning multiple zones: show intersection percentages and allow intentional split/selection rather than automatic guess.
- Uses incompatible with sourced/verified planning constraints, where a formal compatibility matrix exists.
- Display warning labels on geometry and an aggregate issues panel; clicking an issue navigates to its region.
- Explicit `Insufficient authoritative data` state when the system cannot determine compliance.
- Never call a proposed scenario *legally compliant* without source-specific validation and qualified review.

## 5. Building controls and numerical meanings

These are **zoning constraints** and do not automatically generate a complete building or a construction permit.

| Attribute | Meaning | Basic analytic relationship |
|---|---|---|
| **Parcel area** | Land parcel area in m² | Computed from trustworthy projected geometry |
| **Coverage** | Portion of site allowed to be covered by building footprint | `Maximum footprint bound = parcel area × coverage fraction` |
| **FAR (floor-area ratio)** | Floor-area intensity | `FAR area bound = eligible site/land area × FAR`, using the area basis and exclusions defined by the actual regulation |
| **Max height** | Elevation/height control for proposed structure | m, interpreted from correct datum and approved document |
| **Max floors** | Maximum permitted count of storeys | Does not uniquely determine height |
| **Setback** | Minimum horizontal clearance to relevant parcel edge | Front, side, rear; may vary by parcel edge and vertical tier |
| **Skyplane** | Inclined upper spatial limit | Optional advanced 3D envelope geometry |
| **Allowed uses** | Permitted functional uses | Used for scenario classification and compatibility checks |
| **Dwelling-unit density** | Limit/target for homes per defined area | Do not infer without the actual rule's definition |

**Example (illustration, not HCMC law):** a 1,000 m² parcel with 60% coverage and FAR 4.0 has a **footprint bound** of 600 m² and a **FAR-based floor-area bound** of 4,000 m². These are independent upper bounds. Setbacks, maximum floors/height, road rights-of-way, other rules and the precise statutory computation of eligible floor area can reduce what can actually be built. Do not promise 4,000 m² is buildable.

### 5.1 3D building envelope (phase 3)

When trustworthy parcel polygons + max height + setbacks + terrain/ground elevation exist, generate a translucent 3D *buildable spatial envelope* to communicate the feasible outer envelope. **Envelope ≠ allowed total volume ≠ compliant finished building**; FAR and coverage often further restrict a proposed building. Let users toggle it, inspect rules, and compare a proposed design against it. Do not manufacture envelopes based on default heights when metadata are unknown.

## 6. UI/UX layout proposal for UrbanDynamics

### Top header

`UrbanDynamics / Plans / <plan name>` · `Existing | Scenario A | Scenario B` · `2D/3D` · `Undo / Redo` · `Save` · `Compare`.

### Left zoning legend

- Search zoning type.
- Category list with solid fill, label, code and parcel/zone area total.
- Toggles: base zoning, parcel boundaries, overlays, 3D envelopes (when ready), existing buildings and selected scenario.
- Opacity slider controlling zoning fill only (not original basemap labels).

### Map canvas

- Goong / MapLibre basemap remains usable.
- Plan study-area outline, zoning polygons, parcel boundaries, colored fills and hover states.
- Selected area highlighted; correct snapping and semantic zoom; proposed zones visually distinct from official/reference zones.
- Normal map navigation outside active geometry editing.

### Context toolbar

`Select` · `Draw zone` · `Paint parcels` · `Edit geometry` · `Split` · `Merge` · `Delete` · `Measure`.

The active tool owns map pointer events; opening zoning editor must not accidentally trigger Measure Distance/Area/Viewshed or shadow handles.

### Right inspector

Tabs/sections: **Overview** / **Regulations** / **Overlays & overrides** / **Validation** / **Sources**.

Show before/after scenario comparisons and an always-readable source review status.

## 7. Data dependencies for HCMC MVP

| Dataset | Why needed | Necessary for MVP? |
|---|---|---|
| Plan study-area polygon | Scope changes, clip/area | **Yes** (user can draw) |
| Zoning type catalog with *scenario* demonstration rules | Rule selection | **Yes** (can be manually defined, clearly hypothetical) |
| Plan zoning polygons | Render/assign/compare zones | **Yes** (can be user-drawn) |
| Official planning polygons + decisions | Trustworthy existing planning reference | Strongly recommended; missing area shown as unverified |
| Parcel polygons / stable IDs | Paint parcels, parcel-level overrides, per-parcel metrics | Needed for **parcel painting**, not for polygon-draw MVP |
| Verified legal indicators per area | Legal zoning checks | Required before authoritative compliance claims |
| Existing building footprints/heights | Building context and comparisons | Optional in first zoning MVP |
| DEM/ground elevation | Correct 3D buildable envelope | Phase 3 |
| Roads / rights-of-way / frontage | Street-based setbacks and impact | Later; required for those rules |
| Flood, population, transit, land price | Advisory context/analytics | Optional overlays, not official zoning by themselves |

**Crucial for UrbanDynamics:** observed Q1 parcel codes/colors from the earlier parcel sample are **not verified zoning types**. `ODT`, `OTC`, abbreviated building-use labels, current cadastral class, official future land use, and a proposed zoning code should be separately stored and separately labeled. Neither Goong building extrusions nor road land prices determine legal zoning rights.

Official HCMC planning documents often discuss **đất sử dụng**, **mật độ xây dựng**, **hệ số sử dụng đất**, **tầng cao**, and transport/building lines. You may import them as *verified regulations only when tied to a specific adopted plan/decision and spatial extent*. Document scope matters; one area's FAR is not automatically another area's FAR.

## 8. Recommended release phases

### MVP — Zoning editing without claiming regulatory correctness

- Create a small plan and draw a study area in Thủ Đức.
- Existing read-only reference + Scenario A editable.
- Create/edit/copy zoning types with label/color and optional verified numeric parameters.
- Draw, modify, split, merge, delete and assign zoning polygons; handle overlaps explicitly.
- Basic map legend and inspector.
- Plan/scenario persistence, undo/redo and geometry validation.
- A simple dashboard of changed zone areas by category and a disclaimer for unverified proposals.

**Definition of Done:** reload the browser and recover the exact plan/scenario geometry; switching scenarios never changes Existing; edited polygons remain valid; overlap rules are deterministic; labels and legend are correct; missing regulation values stay Unknown.

### Phase 2 — Parcel workflows and zoning constraints

- Parcel painting and per-parcel inspector, only on verified parcel geometry.
- Effective rules from base zoning + ordered overlays + parcel overrides.
- Validate land-use compatibility with documented crosswalk/matrix.
- Robust plan comparison and report/export with sources and review status.

### Phase 3 — 3D and advanced urban analysis

- 3D buildable envelopes based on verified heights/setbacks/terrain.
- Conceptual proposed building masses and ability to check zoning-rule conflicts.
- Estimated capacity / FAR analysis with explicitly stated definitions and uncertainties.
- Shadow, viewshed, flood and transit accessibility studies as separate analyses.
- Publication/review workflow suitable for collaborative planning teams.

## 9. Non-goals for the first Zoning milestone

- Do **not** implement full automatic city-scale 3D building reconstruction.
- Do **not** implement photorealistic roofs/facades, traffic simulation, full geotechnical assessment or AI optimization.
- Do **not** infer legal setbacks/FAR from Goong or sample parcel colors.
- Do **not** overwrite imported official planning datasets when a user experiments with a scenario.
- Do **not** silently reclassify invalid/missing parcel codes.
- Do **not** conflate nominal *land valuation* (road price per m²) with planning rights, construction feasibility, or market property value.

## 10. Acceptance scenarios (business tests)

1. Create study area and Scenario A; Existing remains read-only.
2. Add a `Mixed-use proposal` type and define its sample constraints.
3. Draw a zone and verify label, legend color and area.
4. Draw an overlapping zone: preview replacement/clipping; no competing base zoning on the same area.
5. Split the polygon; two valid features retain original type.
6. Reassign one portion to another type and optionally merge neighboring equal-type zones.
7. Duplicate Scenario A to B; edits to B do not change A or Existing.
8. Click parcel/zone and see the exact rules, source and uncertainty; missing FAR shows `Unknown`.
9. Induce invalid polygon/zone conflict and receive navigable warning.
10. Save/reload/map-style switch without losing geometry; no interference with distance/area/viewshed or Goong map controls.
11. If parcel dataset unavailable, disable parcel painting with an explanation, while polygon drawing remains functional.
12. Proposed types and zones display `Proposal` clearly; approved/reference areas display only documented source status.

## 11. Official ArcGIS Urban documentation used

- Plans — https://doc.arcgis.com/en/urban/12.0/get-started/get-started-plans.htm
- Create a plan — https://doc.arcgis.com/en/urban/11.5/help/help-create-plan.htm
- Work with zoning — https://doc.arcgis.com/en/urban/11.5/help/help-zoning.htm
- Zoning regulation management — https://doc.arcgis.com/en/urban/11.5/help/help-zoning-regulations.htm
- Work with overlays — https://doc.arcgis.com/en/urban/12.0/help/help-create-zoning-overlay.htm
- Work with plan scenarios — https://doc.arcgis.com/en/urban/11.5/help/help-scenarios.htm
- View envelopes — https://doc.arcgis.com/en/urban/12.0/help/help-zoning-envelopes.htm
- Edit a plan — https://doc.arcgis.com/en/urban/12.1/help/help-edit-plan.htm
- HCMC Sở Quy hoạch-Kiến trúc example of area-specific parameters — https://qhkt.hochiminhcity.gov.vn/ban-tin-don-vi/duyet-nhiem-vu-quy-hoach-phan-khu-ty-le-12000-du-an-saigon-sports-city-phuong-an-phu-quan-2-1374.html

---

**Product recommendation:** Implement a **versioned 2D Zoning Editor with trustworthy source/proposal separation first**. Then add parcel painting, overlays/parcel overrides, compliance warnings, and finally 3D envelopes. This keeps the first milestone feasible without misrepresenting unverified HCMC regulations as authoritative.
