# Viewshed — frontend handoff

Updated 2026-10-06. Frontend-only addition; no backend endpoint, database migration,
deployment or secret changes. Existing Distance / Area geometry is unchanged.

## Interaction

The ruler opens **Distance / Area / Viewshed**. Viewshed switches to 3D and suspends
measurement input without deleting its anchors. Click a loaded terrain/building
surface to place the observer, move to preview, then click the target. The observer
starts **1.7 m above the picked surface**; the elevation field is absolute metres
in the existing scene's vertical reference, not a surveyed ellipsoidal altitude.

- Observer circle: translate horizontally, preserving relative terrain height when
  both ground samples are available. Otherwise preserve absolute elevation.
- Observer vertical arrow: change observer altitude, translating the entire view.
- Target arrows: **Heading / Tilt / Distance**, not unrestricted X/Y/Z translation.
  Heading preserves tilt and range; tilt preserves heading and range; distance
  preserves both angles. Drag calculations use a frozen world-axis snapshot to
  avoid feedback/jumps during an edit.
- Drag the far-plane left/right edges to resize horizontal FOV; top/bottom edges
  resize vertical FOV. Opposite edges resize symmetrically around the center ray.
  Observer and target stay fixed; limits remain 5–120°. Small orange/white grips
  mark the edge midpoints. Camera-aligned axes may overlap; rotate the map or use
  the numeric controls when an axis is hard to grab.
- Numeric controls offer keyboard alternatives for position, direction, FOV and
  range. Range stays visible; **Adjust view** expands the remaining controls.
  Valid values update immediately; Enter/blur commits a typed value.
- Done exits editing and keeps the result. Click a frustum edge or observer to edit
  again; observer markers also support Tab + Enter/Space. The Analysis list selects
  existing results. Escape cancels a placement or finishes editing.
- Cancel removes only the unfinished draft. Delete removes the selected result.
  Clear all requires an explicit confirmation. New starts another analysis.
- 2D hides the 3D result, retaining its geographic state. Returning to 3D or changing
  standard/satellite basemaps restores it. Reloading the page does not persist analyses.

Dragging captures the pointer and disables camera handlers until release, cancellation
or unmount. Normal camera navigation does not change observer/target/FOV. UI uses the
existing glass surfaces, icon hover motion and reduced-motion-aware GSAP entrance.
Quality summaries remain visible; expand them for sampling/missing-data details.
The reported green-coverage issue was withdrawn by the user on 2026-10-06; this
interaction update does not change the visibility shader or classification logic.

## Analysis semantics and limits

This is an **approximate loaded-scene visibility analysis**, not a certified GIS
coverage result or a line-of-sight test between only two endpoints. A depth map from
the observer evaluates surfaces throughout a directional frustum. Green means visible
against participating loaded geometry; red/hatching means obstructed. Orange wireframe
and handles are editing overlays and intentionally remain visible through geometry.

Inputs currently supported:

- Loaded DEM samples from the application's terrain source, with its existing datum
  and exaggeration 1.
- The enabled `urban-buildings-3d` layer's loaded Polygon/MultiPolygon footprints,
  including holes, roof and facade triangles. Ground offset matches the existing
  extrusion/picking convention. Heights use positive `max_height`, `height`,
  `render_height` or `building:height`, plus the existing base-height properties.
- If buildings are disabled, transparent, or below their render zoom, the result is
  explicitly **Terrain only**. Visual-only fallback building heights are never used
  as trustworthy analysis heights.

`querySourceFeatures` includes **loaded tiles only**; `isSourceLoaded` is not a proof
of complete coverage around the observer. Distant/unloaded occluders can be absent.
Camera movement can load new geometry and refine colors, but never moves analysis
anchors. Missing DEM/building elevations withhold green classification; known red
occlusions may still be shown. The panel reports incomplete data. GPU/depth failures
show unavailable status instead of claiming a valid visibility result.

Terrain uses a 48 × 48 sampled grid per analysis. Sampling more finely than the DEM
does not increase source accuracy. A 1024 × 1024 observer depth map and depth bias
limit edge/shallow-angle precision. The shadow comparison uses a slope-scaled tolerance
in metres (capped at 5 m along the viewing direction), not a fixed depth-buffer epsilon;
small/near-contact obstructions inside that tolerance can be missed. Local metric Mercator coordinates are appropriate
for the bounded neighborhood, not long-range/geodesic or survey analysis. Refraction,
Earth curvature and transparent-window transmission are not modeled.

Resource limits: **8 analyses**, **1–2000 m center-ray distance**, horizontal/vertical
FOV 5–120°, tilt −89–89°, observer elevation −500–9000 m. Distance defines the frustum's
far plane; its corners can lie farther from the observer than the center-ray distance.
Meshes have a bounded vertex budget and skip unsupported geometry with incomplete status.
These limits protect client RAM/CPU; they are not data-accuracy guarantees.

Custom meshes/3D Tiles do not participate automatically. The current map does not
provide their CPU occluder geometry to this tool. Before adding such layers, supply
their triangles to the scene adapter and integrate their nearest-surface picking;
otherwise they must be documented as unsupported, not silently claimed as analyzed.

## Architecture / integration

`frontend/src/features/map/viewshed/` contains independent math, reducer, scene
adapter, GPU renderer, handles and panel. `Viewshed` stores geographic observer/target
and both FOV angles. Calculations use observer-relative east/north/up metres; the local
origin is applied before conversion to GPU float32. The shared measurement picker is
reused, not replaced. SVG handles are camera-projected hit targets only; frustum and
occlusion are real world-coordinate WebGL geometry, not a DOM polygon.

`createViewshedLayer` accepts a scene provider returning `SceneMesh`: a Float32Array of
local triangle vertices, `complete`, a quality message, and terrain sampling step.
The default provider reads already-loaded terrain/buildings; it does not fetch a new
regional dataset. Earcut 3.2.4 is now a direct dependency for roof polygons with holes
(already used transitively by MapLibre). See [ADR-001](decisions/001-viewshed-loaded-scene.md).

GPU resources are lazy/bounded and released on delete, clear, 2D hiding and style
removal. Mesh/depth uploads are reused on camera-only renders. Source/style changes
invalidate after scene settlement; analysis edits rebuild affected geometry. One map
and one main-scene depth copy serve all viewsheds. No production CPU `readPixels` loop.

For stronger backend-backed coverage, provide spatially bounded geometry with explicit
coverage bounds, dataset revision, source resolution and vertical datum. Supply stable
feature IDs and real heights; do not return rendering fallback heights as facts. Add
cancellable acquisition and cache budgets before expanding beyond the loaded scene.
Persistence would store the geographic `Viewshed` values, not camera matrices or pixels.
No such backend contract or persistence endpoint is implemented in this change.

## Verification

From `frontend`: `npm test`, `npm run lint`, `npm run build`, `npm run test:map`.
The isolated Viewshed browser fixture uses deterministic DEM/building data and the real
MapLibre/WebGL pipeline. It checks placement/preview, green/red obstruction, world
anchors across camera/style/mode changes, numeric editing, handle dragging and camera
handler restoration. Existing distance/area/laser/road tests remain in the suite.
Software-rendered tests do not certify FPS on all hardware or live provider coverage.

Verified: 84 unit/UI tests, 16 deterministic browser scenarios, and four focused
Viewshed repeat runs after the final refinements; lint and production build pass.
Browser color assertions sample the presented image away from editing handles,
not an arbitrary framebuffer left bound by MapLibre's terrain passes.

Reference contracts: [MapLibre custom layers](https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/),
[loaded source features](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#querysourcefeatures),
[WebGL2 depth blitting](https://developer.mozilla.org/en-US/docs/Web/API/WebGL2RenderingContext/blitFramebuffer),
[Earcut polygon triangulation](https://github.com/mapbox/earcut).
