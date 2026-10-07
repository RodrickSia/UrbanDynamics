# Area measurement — frontend handoff

Updated 2026-10-05. No backend, deployment, secret or runtime dependency changes.

## Interaction

The ruler opens a horizontal **Distance / Area** chooser. Area uses the same terrain/building raycast, vertex/edge/face snapping and horizontal height laser as Distance. Select at least three vertices, move to preview, then **Done** to retain the polygon. **Undo** removes the last vertex, **New measurement** starts another polygon with the current units, and **Clear** exits the tool. Choosing the other tool starts a fresh measurement; opening/dismissing the chooser does not discard one.

Completed geographic vertices and acquired elevations survive camera movement, 2D/3D switches and standard/satellite style changes. The 2D view shows horizontal projection; returning to 3D restores the plane calculation when applicable. Vertex spheres are handles/indicators, not draggable editors in this implementation. Holes and multiple simultaneous polygons are not supported.

## Measurement definition

The behavior follows the plane/projection distinction in [ArcGIS AreaMeasurement3D](https://developers.arcgis.com/javascript/latest/references/core/widgets/AreaMeasurement3D/), not terrain-surface integration.

- Convert WGS84 longitude/latitude/altitude to double-precision Earth-centred XYZ, then a local East/North/Up frame at the first vertex.
- If all elevations are available and vertices are coplanar within **0.05 m + 1 ppm of extent**, calculate area and closed perimeter on that 3D plane, including inclined and vertical faces. The UI says **3D plane**.
- Otherwise, calculate **both** area and perimeter from the local horizontal projection. The UI says **Horizontal projection**. Missing elevation also shows **Elevation unavailable**; the visual-only building fallback is never accepted as measured altitude.
- Local-plane measurements are limited to **100 km from the first vertex** and **256 vertices**. Larger/geodesic regional measurements require a separate implementation rather than silently applying this local model. No terrain tessellation/integration is performed.
- Reject nonfinite/out-of-range coordinates, collinear/zero-area polygons, duplicate vertices and self-crossing/touching nonadjacent edges. Invalid previews keep an outline but no area fill/labels; Done validates committed points. Undo or New can recover.
- A terminal duplicate of the first vertex is normalized. Simple concave polygons are triangulated with validated ear clipping; holes are outside this feature.

Units are coherent: Metric autoscales m/km and m²/ha/km²; Imperial uses ft and ft²/acre. Area uses an explicit English locale (matching the application), grouping separators and at most two decimals. Stored metrics remain metres and square metres; unit changes do not modify geometry. Display precision is not a survey accuracy guarantee.

## Rendering and lifecycle

- Existing MapLibre custom layer, with an additional lazily allocated fill shader/VAO/buffer. No second map, DOM polygon, new source tiles or scene reconstruction on pointer movement.
- Orange outline and vertex spheres. Semi-transparent orange/white checkerboard uses polygon-local coordinates in metres, not viewport coordinates. Its physical cell size changes only with polygon geometry, never zoom; derivative filtering averages subpixel cells to reduce aliasing.
- For nonplanar selections, the visualization is horizontally projected at the highest picked altitude with thin connectors to the original vertex handles. This reference plane is not a terrain drape.
- Geometry is rebased around a nearby origin before conversion to GPU float32. Buffers upload only when measurement state changes, not every camera render. Resources are released on custom-layer removal and restored after a basemap reload.
- Two compact dark DOM labels are intentional camera-facing **billboards only**. Their anchors come from world geometry and are projected with the same current matrix as the custom layer. The area anchor lies inside a triangulated polygon, even if concave; perimeter has a short screen-space leader. Pixel sizing does not grow with zoom.
- Existing glass UI/GSAP entrance and hover animations are retained and respect reduced motion. Controls have accessible names, keyboard focus and Escape dismissal; responsive toolbar wraps on narrow screens.

## Building picking / cache fix

Two reproduced failures were corrected: unavailable DEM samples cached as stable building surfaces, and a visible-building snapshot captured before the final terrain/tile render. Unavailable surface/snap geometry is retried, and scene settlement refreshes picking candidates once after a camera/source/style change. Overlay-only idle frames retain the cache rather than repeatedly rebuilding it. Existing tile LOD and RAM cache budgets remain unchanged.

This cannot manufacture source data: trustworthy positive `max_height`, `height`, `render_height` or `building:height` plus DEM elevation are required for accurate building picks. Missing/zero height remains unavailable. The backend/data team should supply actual heights and stable feature IDs, not the rendering fallback. Custom object picking is limited to geometry already supported by the shared picker; no new mesh provider is introduced.

## Files and verification

- `utils/measurementAreaFrame.ts`: WGS84 local frame.
- `utils/measurementArea.ts`: plane selection, validation, area/perimeter and triangulation.
- `utils/measurementAreaRender.ts`, `layers/areaFill.ts`, `layers/measurementLayer.ts`: world geometry and fill lifecycle.
- `components/MeasurementSelector.tsx`, `AreaMeasurementToolbar.tsx`, `AreaMeasurementLabels.tsx`: UI/billboards.
- `hooks/useMapWorkspace.ts`: tool state and finish validation.

Run from `frontend`: `npm test`, `npm run lint`, `npm run build`, `npm run test:map`. Optional real-provider checks: `npm run test:map:live` (network/data availability required). Tests cover inclined/vertical/concave/nonplanar polygons, invalid rings, unit conversions, UI lifecycle, world-label projection, GPU buffer reuse and basemap persistence. Software-rendered browser results do not imply a hardware-independent FPS guarantee.

Verified for this change: 75 unit/UI tests; 14 deterministic browser scenarios, with three focused reruns after the final cache/mobile refinement; lint and production build. Two live checks also passed: a positive-height HCMC building was picked at its visible surface, and a Ben Tre footprint with `max_height = 0` correctly remained unavailable for true elevation. This does not certify every building in the provider dataset.
