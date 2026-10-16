# Urban planning assistant — guide

Updated 15 October 2026. Branch: `feat/development-simulation-context`.
Preview: **http://127.0.0.1:8192/**, tunneled to server 156 port 51875.
This preview uses separate plans, sessions and results, with read-only access to
the team warehouse. It does not replace main.

## What the assistant does

**16 October addition:** [Structured dataset query guide](agent-structured-dataset-query.md).
Three new tools (`dataset_describe`, `dataset_query`, `dataset_query_refine`) bring
the model's registered tool count to **32** at that stage. They support typed filters, spatial
source joins, sorting/grouping/aggregation, a filtered map/table and five recent
queries per session. The guide documents bounded coverage and unknown values.

The subsequent [PostGIS/Goong/scope upgrade](agent-query-routing-upgrade.md)
brings the current total to **34** tools and pushes warehouse filtering/counts
before display limits, with explicit coverage for non-warehouse adapters.

The robot button below **Data Layers** opens the assistant. Hard refresh with
Ctrl+F5 after a deployment. The interface is English and replies follow the
language of your question. You can use it without opening a Development plan.
**Enter sends; Shift+Enter inserts a new line.** Enter during IME composition
does not send the unfinished text.
Your message appears immediately in the chat, followed by **Model is thinking…**.
The input clears while the request runs. The stored response replaces pending
state without duplicating your message; if the request fails, the question stays
visible and is restored to the input for retry. `scripts/check-agent-chat-feedback.cjs`
checks these transitions with delayed/failing intercepted responses and no model calls.

### If the basemap is blank

The preview now starts at the Thủ Đức study neighborhood. If Goong returns
401/403/429 or a provider server error, it switches once to a visible-browser
OpenStreetMap raster basemap and shows a notice. The alternate map preserves the
camera, dataset overlays and assistant; it does not supply Goong vector POIs or
3D building geometry. Agent POI queries can still use the installed source
supplement. A manual basemap change retries the selected Goong style.

The fallback uses ordinary browser tile requests/cache, with visible OSM
attribution; it does not bulk download or prefetch maps. See the
[OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

### Prices and amenity-based house search

`layer_query` queries connected dataset layers even when hidden on the map.
For land prices it queries a disclosed buffer around the analysis area or source
parcel, ranks actual nearby road-segment records and preserves price/unit/date
and match metadata. This addresses the old intersection-only area summary, which
could miss a reference road beside a parcel. Road-table references are not market
prices or verified frontage assignments. Use a parcel ID or a narrow map extent
for meaningful proximity; a large area can contain many unrelated reference roads.

Example: **“What are the land price references in the selected area? Show prices,
units and effective dates.”** The visible Dataset evidence panel lists records;
the chat/tool result and exported report preserve source metadata.

`amenity_site_search` uses the system's **Points of Interest** vector source:
the browser queries loaded POI tiles and passes bounded point properties to the
backend. It classifies explicit category/type tags, not business-name guesses.
Loaded tile coverage depends on viewport and zoom, so it is not a complete city
POI database. `layer_query` with `poi` can inspect these actual source points.
For coverage beyond loaded tiles, an installed OSM extract or bounded Overpass
request supplements them; each matched amenity records its source. Clinics are
not silently substituted for hospitals. It evaluates up to 250 source parcels and returns up to six
sites with nearest amenity name, OSM ID, distance, threshold and pass/fail. This
is a bounded area/ID sample rather than all-city optimization. OSM completeness,
current operating status, entrances and walking routes are unverified.

Example: **“Find me a place to build a house for 4 people in the currently selected area. It should be near
supermarkets, parks, and hospital.”** Without a stated budget/plot size/radius,
the agent can offer an exploratory search in the explicitly chosen neighborhood,
disclosing provisional 40–1,000 m² parcel bounds and 1 km proximity filters.
These are screening defaults, not planning standards or a measured requirement
for four people. Household size does not establish an adequate house design.
If geographic scope is absent, the agent asks for a neighborhood/district or
confirmation to continue the prior area/use the visible map. It must not silently
use the viewport or a saved area as if it were a citywide search.
Budget, neighborhood, plot size and floors refine the search; building program
inputs are still needed before simulation. If no site passes every proximity
filter, partial alternatives are explicitly labeled. Distances are straight-line
from an interior parcel point to mapped POI geometry, not walking travel times.

The POI request including the proximity buffer is limited to 80 km². Zoom into
a neighborhood for this search. Results require source parcels in the warehouse;
POI availability does not supply missing parcel geometry or legal/vacancy status.
The provider can be changed with `AGENT_OVERPASS_URL`. No POIs are invented on
provider failure. Attribution and capture time appear in the panel/report.

### Street/alley requests and search scope

You can name a street/alley directly without opening a plan or selecting a parcel.
For example: **“tìm khu vực để xây căn nhà 4 tầng ở hẻm 114 đường trần quốc tuấn
quận gò vấp”**. `area_select` with `source=street` first queries the team's actual
`transport.sumo_edge` names/geometry, including unaccented name matching. It
prefers exact alley 114 over branches 114/2 or 114/14, and separates distant
homonyms. Ambiguous matches require selection before the search area changes.

A unique match selects a disclosed **100 m buffer around the mapped centerline**,
not an exact address, legal alley boundary, legal frontage or known vacant land.
The agent then searches source parcels, reporting area/land use and straight-line
distance from a parcel interior point to the requested street. A stated four-floor
house is proposed input, not proof of permitted height. Missing floor area/occupancy
must not prevent preliminary site search, but are required before a full simulation.

Search extent is saved until changed. For a new location-free site search, the
agent must ask whether to reuse it or specify another district/neighborhood.
“Use the current map view” explicitly selects the viewport; moving the map alone
does not change the saved search area. A request for all HCMC cannot be answered
by silently using one viewport: coverage and bounded sample limits must be disclosed.

### Installed POI supplement

The isolated preview has an OSM/BBBike Saigon extract, source modified
**10 October 2026**, downloaded and checksum-verified on 15 October. It contains
305 supermarket, 856 park and 144 hospital node/way records. These are mapped
records, not unique verified operating facilities. Relation-only objects are not
assembled. Source extent: **106.54–106.85°E, 10.66–10.89°N**; it does not cover
all of expanded HCMC. The source coverage polygon must cover the requested query
before the offline supplement is used. Public Overpass remains a fallback outside
that coverage, and can be unavailable/rate-limited.

Provenance: [BBBike Saigon directory](https://download.bbbike.org/osm/bbbike/Saigon/),
`Saigon.osm.pbf`, published MD5 `427bbf0cf9a8917376753ca3f85264ba`, SHA-256
`3de1c4cf89bfca93263b001c1a43b0a926e0a60b5c568a3ac33088eee9e5dfb5`.
Importer: `scripts/import-agent-pois.py` (optional `osmium>=4,<5`; not a runtime
backend dependency). JSON installed in the dedicated preview volume at
`/runtime/agent-pois/offline-bbbike-saigon.json`. The model key is not involved in
downloading or querying these source records.

### All system dataset layers

`source_catalog.queryable_layers` is the agent's complete adapter list. It includes
all vector layers in `repository.LAYER_INFO`, plus the raster and traffic adapters.

| Web dataset | Agent source ID | Query behavior |
|---|---|---|
| Population | `population` | Explicit WorldPop year; modeled people, coverage and unknown total below 99% coverage. |
| Flood risk | `flood_risk` | Actual matching features and source properties. |
| Flood history | `flood_history` | Observed/reported source records; optional supported dates. |
| Satellite flood | `flood_satellite` | Classification source features; not flood depth. |
| Land prices | `land_price` | Nearby reference roads; preserve units/date and unreviewed automatic allocations. |
| Parcels | `parcels` | Source parcel attributes; no inferred vacancy/ownership. |
| Synthetic buildings | `synthetic_buildings` | Existing generated building layer, explicitly synthetic. |
| Traffic | `traffic` | Existing historical-profile endpoint, explicit weekday/hour; not live flow. |
| SUMO network | `sumo_network` | Static network source features. |
| SUMO simulation | `sumo_simulation` | Existing saved `run_id` output, or run catalog when omitted; no solver launch. |
| Points of Interest | `poi` | Existing system POI tile features; installed source supplement if no map snapshot exists. |
| Extra vector sources | `hcmc_boundary`, `hcmc_regions`, `rainwater`, `flood_satellite_catalog` | Shared repository APIs with installed-source availability preserved. |

A supported adapter does not mean every layer has matching records at every
location/date. Source absence/unavailability stays explicit. Pure visual controls
(terrain, basemap style, road-width display) are not independent measured datasets.

| Task | What happens | Main tools |
|---|---|---|
| Understand the system | Reads installed capabilities and sources; distinguishes available services from loaded data. | `platform_overview`, `source_catalog` |
| Choose an area | Uses the visible map, saved plan, a source parcel, explicit bounding box or public place name. Moves the map to the selected area. | `area_select` |
| Explain an area | Queries population, mapped buildings, roads, facilities and matching environmental/reference layers; records source, year and limitations. | `area_analyze` |
| Find candidate sites | Searches real warehouse parcels by area and optional land-use code; draws candidates on the map. | `candidate_search` |
| Compare sites | Scores explicit criteria and weights, shows missing evidence and proxy threshold failures. | `candidate_compare` |
| Review a saved plan | Checks saved zoning/Development inputs with the shared validation and available indicators. Proposed limits are distinguished from official requirements. | `planning_review` |
| Compare the same project at different sites | Fits the same declared program on 1–3 parcels, prepares immutable inputs, starts an asynchronous study and reads results. | `candidate_study_prepare`, `candidate_study_start`, `urban_results` |
| Edit a Development plan | Opens/creates plans, duplicates scenarios, edits saved buildings/floors and proposed zoning through validated commands. | See [Development tools](development-ai-agent.md). |
| Explain/export evidence | Combines area sources, comparison criteria, unresolved questions and completed solver outputs into downloadable Markdown. | `urban_report` |

Map-layer visibility and focus controls, source inspection, saved Development
simulation, and paired hypothetical improvement checks remain available.
The assistant uses bounded application tools, not arbitrary SQL or shell access.

## Try it without a plan

1. Move the map to the study area and open the robot button.
2. Ask: **“Phân tích vùng đang xem bằng WorldPop năm 2026. Tìm tối đa 3 thửa
   từ 2.000 đến 20.000 m²; so sánh theo diện tích, khoảng cách tới đường và
   footprint hiện hữu. Ghi rõ tiêu chí, nguồn và dữ liệu còn thiếu.”**
3. Expand **Area evidence**, **Candidate sites** and **Site comparison**.
   Candidate boundaries and IDs are drawn in orange. A source parcel is not
   automatically vacant, accessible, available for purchase or legally suitable.
4. Ask for the same project at two sites, with a complete program, for example:
   **“Dùng hai ứng viên đầu trong kết quả tìm kiếm. So sánh cùng một trường học
   3 tầng, tổng diện tích sàn 600 m², cao tầng 3,2 m, khoảng lùi đề xuất 1 m,
   10 nhân viên, 100 người dùng mỗi ngày, công suất 100 chỗ; mưa 60 mm.
   Chạy screening và ghi rõ các giả định.”**
5. Choose the **Site study** run in the assistant result selector. The worker
   updates status and result tables without repeated model calls. Ask for an
   explanation after completion; use **Download evidence report** to export.

If an exact floor program does not fit, preparation reports the rejected site.
It does not silently reduce floor area or change the project to make it fit.
The automated footprint is a square fitted inside the parcel with the stated
setback and tested rotations: preliminary placement, not architectural optimization.

“Thủ Đức” can identify the current ward rather than the former city. Named-place
selection displays the returned name and bounding box. Check it before searching.
It is a search extent, not an administrative or legal boundary.

## Data actually used

| Evidence | Source / method | Interpretation and missing data |
|---|---|---|
| Parcel geometry and area | Existing team `parcels.plot`, or `parcels.land_plot` fallback; land-use palette where installed. | Actual source geometry. Vacancy, ownership, acquisition rights and legal approval are unverified. |
| Population | Installed WorldPop raster for the explicitly requested year; area-weighted intersection. | Modeled population, not census. Publishes total only at ≥99% coverage; otherwise partial sum and unknown total. Missing requested year does not silently become a future projection. |
| Existing building evidence | Overture mapped footprints clipped to the area; union prevents overlapping area double counts. | Footprints do not establish use, floors, occupancy or demolition floor area. More than 2,000 matching records is flagged as truncated. This area summary is not a new complete simulation baseline inventory. |
| Roads | Installed OSM-derived SUMO edge geometry and nearest mapped road within 1 km. | Straight-line proximity, not verified entrance access, vehicle counts or travel time. Directed edges are not unique streets. |
| Facilities / transit | Existing covering OSM services and installed transit snapshot. | Mapped presence/coverage does not provide available school places or capacity. Missing snapshots remain unknown. |
| Flood / rainfall / land-price references | Existing team source services; bounded query followed by geometry filtering, optional dates on time-enabled sources. | No matching record does not mean safe. Flood risk/classification is not surveyed flood depth. Reference land prices are not market or compensation estimates. |
| Traffic profile | Installed historical traffic route, explicit ISO weekday/hour; default Tuesday 18:00. | Historical profile, not current traffic. |
| Ground cover | Existing WorldCover/OSM ground-context pipeline, including disjoint MultiPolygon parts. | Historical/mapped cover; fallback estimates remain labeled. |
| Utility and school capacity | Existing context if available; otherwise unknown. | No invented available electricity, water, drainage capacity or existing school seats. Another team member is integrating these datasets. |
| Study traffic background | Common declared traffic prior for all alternatives. | The transferred UIT counting prior is a scenario assumption outside its source camera location/time, not a measurement on every city road. |

The area profile limits source samples and reports truncation. It is an evidence
summary, not exhaustive extraction of all city features.

## How site comparison works

Supported metrics are parcel area, modeled population density, mapped-road
distance, clipped mapped footprint area, mapped transit coverage and mapped green
area. Each criterion declares minimize/maximize, a positive weight, and optionally
a proxy threshold.

- Scores use relative min/max normalization among the selected candidates;
  ties score 50 for that criterion.
- Only metrics known for **every** candidate enter the weighted score. A missing
  metric is excluded for all sites, never replaced with zero or rewarded.
- At least two common criteria are required for a priority order. Otherwise the
  response says that comparable evidence is insufficient.
- Search returns a bounded area-ordered sample, not the best sites in the city.
  Comparisons accept 2–6 explicit sites. Search returns at most 12 candidates.
- Passing declared proxy thresholds is not planning approval. Missing capacity,
  ownership, vacancy and calibrated traffic remain unresolved requirements.

## How studies connect to the simulation

The general assistant supports residential, office, school and hospital programs.
Residential input must include residents and housing units; other uses require
staff and daily users. School/hospital programs also require proposed service
capacity. These quantities must be supplied or explicitly agreed, not inferred
as measured occupancy.

Studies use the shared `PlanningStudy` site-selection mode with equal-program
targets. Each alternative keeps the same declared floor program, weather and
background traffic prior. Screening produces demand, runoff and shade estimates;
unknown baseline occupancy/capacity stays unknown. It cannot establish real spare
capacity, displaced users, existing school shortage or net building replacement
impact without the missing baseline inputs.

Detailed mode acquires one common local OSM network around the sites and runs
before/after on shared background assumptions. It retains the prepared project
geometry and program instead of reloading/changing them while starting native.
Enable **Allow detailed SUMO/SWMM runs** first. The existing local-network limit
is 25 km²; distant candidates may need separate or narrower studies. Native is
limited to 24 SUMO runs per request. Repeated starts of the same study/mode reuse
the owned job. Sessions permit up to 12 general jobs.

Results are saved separately from editable Development buildings. General
school/hospital placement does not automatically create a floor-editable building
in the main Development UI. The assistant can still create/edit supported
Development plans through the existing plan tools.

Incomplete-trip SUMO delay is not treated as a valid improvement. Reports preserve
comparison status and incomplete-trip counts rather than interpreting an unknown
delta as zero. Native outputs remain scenario results until calibrated locally.

## Sources, persistence and deployment

- Source year, selected geometry, comparison criteria, prepared programs and owned
  job IDs persist in the preview session database. Refresh/reload restores them.
- Public sessions expose results/context, never model credentials. The model key
  is backend-only; frontend and worker do not receive it.
- Existing plan revision/unsaved-change checks and validated edit commands remain
  in use. Creating an alternative should duplicate the scenario before editing.
- Named-place lookup is user-triggered, Vietnam-filtered, cached, bounded to three
  results and rate-limited to at most one provider request per second. The public
  Nominatim endpoint can be replaced through `AGENT_GEOCODER_URL`; see its
  [usage policy](https://operations.osmfoundation.org/policies/nominatim/).
  Do not use this fallback for bulk geocoding or personal addresses. OSM
  attribution is displayed for the returned area.
- Selected area bounding boxes are limited to 600 km². Full-city analysis should
  be divided into appropriate study areas rather than implying exhaustive data.

Implementation: `backend/app/services/agent/general_tools.py`, the shared agent
schema/service/store, and `frontend/src/features/agent/DevelopmentAssistant.tsx`.
Verification and reproducible scripts: [test report](urban-ai-agent-test-report.md).
