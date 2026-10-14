# Development repair

Requested: read baseline building metrics, prefer scenario zoning in parcel selection, merge the latest simulation branch, simulate selected parcel by default with a whole-scenario option, stabilize 2D/3D, and simplify the plan dashboard.

Findings: the parcel report only measured `scenario.buildings`, so Existing returned proposal zeros; simulation controls were hidden until a proposal building existed; mode changes removed/recreated generated and Goong layers, and deferred clipping plus paint transitions could flash buildings outside the study area. Latest simulation commits `de00136` and `0c8ac24` merged without conflicts.

Baseline source: generated parcel buildings already used on the map. Their geometry/floors/heights produce estimated GFA/FAR/coverage; no matching record is unknown, not an empty surveyed site. Goong tile attributes are streamed context, not cadastral observations. Proposed zoning is shown separately from underlying parcel use.

Rendering: retain Goong/generated sources and change visibility in 2D. Building layer owners synchronously notify plan clipping after a paint/layout change; MapLibre's `styledata` event alone arrives after paint evaluation and can allow a frame of the original geometry. Clipped sources retain their identity across mode changes, with opacity transitions disabled and geometry refreshed only when inputs or source tiles change.

Simulation failures reproduced from the saved plan data:

- One saved footprint shared a parcel boundary but failed strict containment after coordinate round trips. The projected outside area was about `3.55e-12 m²`. The engine now permits only numerical roundoff bounded by both 10 micrometres and 1 square millimetre; a regression test still rejects a centimetre-scale displacement outside the site.
- Two cadastral source parcels overlapped by `0.308 m²`, so treating each as an independent simulation project failed overlap validation. Whole-scenario runs now use a single study-area site, counting land once. Selected-parcel runs retain that parcel's clipped site.
- Generated buildings are frozen into the baseline, with estimated occupancy. A selected parcel can run without a new proposal. Missing baseline data remains unknown. Whole-scenario comparisons retain unknown occupancy because only developed parcels have a frozen baseline inventory; this is not a complete survey of every building in the study area.

The bridge retains engine bounds: at most six developed parcels and twenty buildings per run, connected polygon sites, and the engine's site-area limits. Proposed building programs replace the modeled site program. Occupancy, open-space surfaces and utility capacity remain assumptions or unknowns, not observed infrastructure measurements. The merged Vietnam planning catalog is reference screening, not a verified site approval.

Read-only diagnostics succeeded through `http://127.0.0.1:51873/api`; the direct API tunnel and SSH were unavailable. Copies of the plan and matching generated building records were used locally. Screening passed for Scenario A and a selected parcel; SUMO + SWMM passed for Scenario B. No remote plan data was modified.

Verification: backend suite **354 passed**, **8 skipped** because an isolated PostGIS database was unavailable. Frontend lint/build and **129 unit tests passed**. All **five browser flows passed** across targeted runs, covering baseline metrics, zoning precedence, per-floor programs, scope selection, result restoration, Dashboard controls, and cached 2D/3D clipping. The long lifecycle test was split into independent persistence and editing flows; a redundant full-scene screenshot that stalled headless SwiftShader capture was removed without removing functional assertions. UI screenshots were inspected separately. Browser/API/worker fixtures run in isolated local storage. No deployment or push.
