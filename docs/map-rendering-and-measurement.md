# Map rendering and measurement maintenance

Updated 2026-10-05. Frontend-only; no API, secrets or deployment changes.

## Metric road widths, without decorative textures

Only asphalt textures and custom lane markings are removed. Estimated metric width is retained in both 2D and 3D by modifying the provider's existing carriageway width/gap paint, without adding surface layers, images or marking geometry. Native colors and symbols remain unchanged. This does not change endpoint-based distance calculations, snapping, laser guides or measurement labels.

Estimates per supplied carriageway: motorway 22 m, trunk 18 m, primary 14 m, secondary 10 m, tertiary 8 m, street 7 m, service 4 m; links 6–7 m. These are illustrative widths, not surveyed boundaries. Ground roads and bridges use the same metric scale; rail, pedestrian, runway and tunnel layers are untouched. Satellite imagery is not restyled.

From zoom 16 onward, a camera-only exponential width expression scales by `2^zoom`, including fractional zoom and overzoom past the source's maximum zoom. This avoids feature-dependent widths varying with terrain tile LOD. Overview stop values remain cartographic. Latitude correction uses the map centre and refreshes after a 0.05-degree latitude change at move end, rather than reparsing styles every zoom frame. Existing gapped casings follow the carriageway's width; solid casings add an illustrative 0.5 m edge on each side.

## Basemap and camera fixes

- MapLibre style diffing retains custom layers while appending new basemap layers. The measurement layer must be moved to the top after style load and scene-layer updates; otherwise an opaque satellite raster hides its GPU markers/lines. React measurement state and acquired world coordinates are retained.
- Style readiness gates layer installation during swaps. Only the style-load handler creates a missing measurement layer; pointer updates continue storing geometry without attaching to an outgoing style.
- Basemap changes and building-opacity changes preserve the camera. Only a mode change schedules the pitch flight, after the new scene pipeline's first render. Bearing is preserved and MapLibre's reduced-motion handling remains enabled.
- Reapplying enabled terrain is idempotent. The separate terrain and hillshade DEM sources remain intentional; exaggeration stays 1.

## Retained resource budget

- Composite vector source LOD parameters: `4, 3` to retain distant buildings while bounding detail.
- Unused tile cache: maximum 64 tiles per source and two zoom levels. Visible tiles are managed separately; this is not a total RAM cap.
- Measurement geometry uploads only after state/geometry changes, not on every camera frame.
- The viewport-sized laser depth texture is created lazily and released when measuring completes or switches to 2D.

## Building data contract

The picker requires positive `max_height`, `height`, `render_height` or `building:height`, plus available ground elevation, for a valid roof/facade elevation. Buildings without height still have a 12 m **visual-only** extrusion. They must remain `Elevation unavailable`; reporting that fallback as an actual measurement would fabricate data. Backend/data providers must supply trustworthy height and stable feature IDs to make these buildings measurable. A screenshot alone cannot establish whether a particular building is missing data; reproduce at its coordinates.

## Verification

From `frontend`: `npm test`, `npm run lint`, `npm run build`, `npm run test:map`; live Goong/DEM checks: `npm run test:map:live`.

`workspace.spec.ts` mounts the actual UrbanMap component and checks repeated standard/satellite switches with screenshot pixels for the red preview, stable committed anchors, camera preservation, a single monotonic mode flight, and metric road width at fractional zooms with terrain while preserving the native color and absence of custom textures/markings. Synthetic vector tiles use test-only `@maplibre/geojson-vt` and `@maplibre/vt-pbf`. The layer-order regression returns zero marker pixels when the fix is removed. Existing suites cover roof/wall/edge picking, unknown-height fallback, laser, multipoint measuring, world anchoring, labels and GPU upload reuse.

Software-rendered browser tests do not establish a device-independent FPS guarantee; first-time shader compilation and remote tile latency can still affect the initial 3D transition.
