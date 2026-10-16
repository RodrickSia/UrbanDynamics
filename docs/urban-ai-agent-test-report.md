# General urban assistant — verification

Date: 15 October 2026. Branch: `feat/development-simulation-context`.
Server preview: 156, loopback web 51875, workstation tunnel 8192. Main and the
shared warehouse schema/data were not changed by this implementation.

## Latest: dataset adapters, system POIs and keyboard (15 October)

### Named alley and explicit geographic scope

Latest backend regression: **41/41 passed**, including exact-alley versus branch
matching, distant homonyms, unavailable road data, Vietnamese name normalization
and model-tool scope enforcement. The legacy plan-only `site_search` is no longer
advertised to the model; old direct callers without a plan use the general source
search for compatibility.

`scripts/check-agent-street-search.py` passed both real-model turns. With an
unrelated Thủ Đức viewport, the exact request for a four-floor house at Hẻm 114
Trần Quốc Tuấn resolved the real alley near 106.690°E, 10.821°N from eight named
source edge records, then queried real source parcels in a disclosed 100 m buffer.
The direct source test returned six parcels; the model requested a bounded sample
of twelve. Example modeled reply: parcel `1545835`, ~40.2 m² and ~3.6 m from the
mapped centerline using an interior point. This is not verified entrance access,
vacancy or permission for a four-floor house.

The next location-free request for sites near hospitals/parks caused attempted
implicit selections to be rejected at the backend model-tool boundary. The model
then asked whether to continue around the named alley or choose the visible map.
No new candidate search executed for that unconfirmed scope. The scope question
and selected named area were restored in the live browser; **3/3 browser checks
passed**, and the screenshot was inspected.

Evidence: `street-search-result.json`, `street-browser-result.json`,
`street-scope-desktop.png`. Reproduce via `scripts/check-agent-street-search.py`
(paid model calls) and `scripts/check-agent-street-browser.cjs` (no new model call).

### Startup fix after reported blank map

Reproduced on a fresh browser session: Goong's style URL returned HTTP 429,
leaving controls over an empty canvas. Added a one-time OpenStreetMap raster
fallback for Goong authorization/rate/server errors, visible attribution and
provider notice; scoped CSP permits the fallback tile/font origins. Preview
starts at the Thủ Đức study neighborhood.

`node scripts/check-map-startup.cjs --force-goong-429` passed: 27 fallback tiles
loaded, provider notice/attribution present, assistant opened without page errors.
The normal fresh-session check also passed with the real Goong 429: 24 fallback
tiles loaded and no page errors. Screenshots were inspected.
Evidence: `startup-fallback-result.json`, `startup-result.json`,
`startup-forced-fallback.png`, `startup-fresh.png` in the same evidence directory.

### Dataset integration results

Chat feedback update: `scripts/check-agent-chat-feedback.cjs` passed **6/6**
checks on the deployed preview: immediate user bubble before the response,
thinking indicator beneath it, cleared/disabled composer, no duplicate on success,
retained question/retry text on failure and no page errors. Welcome suggestions
hide as soon as sending begins. This uses intercepted delayed/failing responses,
not paid model calls. Evidence: `chat-feedback-result.json`, `chat-thinking.png`.

- Backend agent regression: **34/34 passed**; frontend TypeScript/Vite build passed.
- New browser regression: **8/8 passed**, covering price/amenity evidence,
  Enter sends once, Shift+Enter newline, IME composition does not send, actual
  system POIs in the chat request, server POI query and no page errors.
- Captured **233 actual system basemap POI points** in the loaded viewport and
  successfully bound/queried them through the backend. Cluster labels are excluded
  from individual amenity qualification. Generic shop icons are not automatically
  called supermarkets. Warehouse inspection found no application POI table;
  `tiger.place`/`tiger.place_lookup` are geocoder reference tables, not this map's POI source.
- All **10 web dataset adapters**, plus POI, returned HTTP 200 in the live matrix.
  This checks adapter connectivity, not positive matching records everywhere.
  Three additional vector sources (boundary/regions/rain) also returned 200.
  Extra `flood_satellite_catalog` is not installed in the connected source and
  returns explicit unavailable/422; the web's actual `flood_satellite` layer is connected.
- SUMO simulation lookup returned `not_precomputed_for_requested_period` for
  Tuesday 18:00. The adapter reads existing cache/run outputs; it does not start
  a solver to fill missing data. Explicit run IDs and cached periods are supported.
- Price query retrieved 20 displayed records from a bounded nearby-source query,
  preserving effective date, units and unreviewed automatic match metadata.
  The real model correctly identified differing source/mapped road names and did
  not describe those allocations as verified parcel/market prices.
- The exact English request “Find me a place to build a house for 4 people. It
  should be near supermarkets, parks, and hospital.” invoked `amenity_site_search`.
  The selected Thủ Đức extent had 25 source parcels in the screening size range
  and **no all-criteria match**. The model returned labeled partial alternatives,
  source distances, missing hospital evidence and unknown legal/vacancy status.
  These test results do not establish that there are no suitable sites elsewhere.
- A real OSM tagging conflict (pet shop labeled supermarket) was caught. An
  explicit-name conflict check now excludes such POIs from qualification; source
  tags are preserved and exclusions reported. Clinic/health-station names are
  not silently qualified as hospitals. This is a bounded quality check, not
  validation of every POI's real-world operating status.
- Two new natural-language model turns returned English without forcing a reply
  language. Provider failures were observed before the local OSM supplement was
  installed; they were not converted into invented amenities.

Reproduce with `scripts/check-agent-layer-matrix.py`,
`scripts/check-agent-datasets.py` and `scripts/check-agent-datasets-browser.cjs`.
The dataset model script can reuse a previously captured real map POI snapshot
from the browser evidence, and makes paid model calls. Keyboard behavior is
tested with an intercepted chat response, without a paid extra model call.

Local evidence under `test-results/general-agent/`:

- `layer-matrix.json`: every adapter's HTTP status, properties and source metadata.
- `datasets-result.json`: real tool results, exact prompts, model responses/traces.
- `datasets-browser-result.json`: eight browser checks.
- `system-pois-browser.json`: actual bounded POI snapshot sent by the browser and
  returned source query; no model/provider credentials.
- `datasets-desktop.png`: inspected screenshot of dataset and amenity panels.

POI supplement provenance and all source IDs: [assistant guide](urban-ai-agent.md).

## Earlier general integration checks

| Check | Result | Scope |
|---|---|---|
| Backend agent regression | **22/22 passed** | General tools plus existing Development agent tests; missing-source handling, shared-criteria scoring, ties/thresholds, exact program, source order, Decimal/date persistence, explicit population year, named-place caching, MultiPolygon cover, job ownership/idempotency and frozen native inputs. |
| Frontend regression | **6/6 passed** | Existing DevelopmentSimulation/usePlanSimulation suites during this integration. |
| Frontend production build | Passed | TypeScript and Vite; deployed as a separate preview build. |
| Live warehouse + screening worker | Passed | No-plan area → real source parcels → comparison → same school program at two sites → completed shared worker job → actual solver outputs → report. |
| Real Luna natural-language workflow | Passed | Two Vietnamese turns orchestrated source queries, search, scoring, preparation and start. One invalid field name was rejected by validation; the model corrected it before study creation. |
| Browser | **9 workflow checks passed** | No plan required, restored area, candidate comparison, two result tables, Markdown download, completed outputs in export, reload, mobile table fit and no page errors. Additional visual checks cover text clipping and assistant controls. |

Browser screenshots were inspected: the basemap, orange source parcels and IDs
render; comparison text wraps. Map focus is applied after map initialization,
including a restored no-plan session. Mobile panel stacking keeps map controls
from obscuring the assistant.

## Real-data example

The tested map extent was around the existing Thủ Đức parcel demo:

- Explicit WorldPop **2026** source: `worldpop_hcmc_2026.tif`.
- Modeled population **1,501.49**, raster coverage **99.884%** for this extent.
- **197 mapped Overture footprints**, clipped union **71,523.51 m²**.
- Search returned source parcels `1937234`, `1937204`, `1937233`, `1937214`,
  `1937203`, `1937205`. This is a bounded sample, not vacant-land certification.
- The same program was prepared on the first two search results: school,
  3 floors, 600 m² GFA, 3.2 m floor height, proposed 1 m setback, 10 staff,
  100 daily users, 100 proposed places and 60 mm rain.
- Live screening job `a07027d3-031d-43d3-bdb2-0afc932fc616` completed. Its two
  alternatives produced approximately +0.60 m³/event screening runoff delta;
  estimated neighboring shade differed by site. These are modeled impacts, not
  evidence that either source parcel is legally or operationally preferable.
- The natural-language regression used the same **first two search IDs**, not a
  reordered score list, and created job `ceb298dd-b92d-4063-bf60-30f5039b0cc0`.
  Completion and report contents were subsequently checked in the browser.

Named-place lookup was separately exercised for “Thủ Đức, Hồ Chí Minh”. It
returned **Phường Thủ Đức** with a provider bounding box. This confirms why the
returned name/extent must be checked rather than assuming the former city boundary.

## Reproduce / evidence

Run from this worktree with the existing preview tunnel and configured backend:

```sh
docker start -a general-agent-tests
python scripts/check-general-agent.py
python scripts/check-general-agent-model.py
node scripts/check-general-agent-browser.cjs
```

The preconfigured test container mounts this worktree. For a fresh environment,
run `backend/tests/test_general_agent.py` and `backend/tests/test_development_agent.py`
with the repository's backend/ETL dependencies and paths.
The model script calls the configured paid model; browser polling does not.

Evidence (local ignored artifacts):

- `test-results/general-agent-backend.xml`
- `test-results/general-agent/live-result.json`
- `test-results/general-agent/model-workflow.json`
- `test-results/general-agent/browser-result.json`
- `test-results/general-agent/browser-export.md`
- `test-results/general-agent/general-desktop.png`
- `test-results/general-agent/general-mobile.png`

## Practical limits

This verification ran a new end-to-end **screening** study. Native input freezing,
authorization and shared-engine routing are covered by tests; a new full SUMO/SWMM
benchmark across general-agent alternatives was not run. Existing Development
native results remain available separately.

No new measured utility capacity, existing school seats, baseline occupancy,
ownership/vacancy or calibrated local OD/counts were added. Area footprint queries
do not constitute a complete demolition/occupancy ledger. General recommendations
are conditional on the reported criteria and missing evidence.
