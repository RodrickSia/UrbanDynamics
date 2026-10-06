# ADR-001: Observer depth maps for interactive loaded-scene Viewshed

## Status

Accepted for the bounded frontend feature; complete regional coverage is not claimed.

## Date

2026-10-05

## Context

The map uses MapLibre terrain and extruded buildings, with existing world-space
measurement picking and light-glass UI. Viewshed must continuously classify a 3D
viewing volume, preserve anchors during camera/basemap changes and avoid replacing
working measurement tools. There is no backend occluder/coverage service yet.

## Decision

Build a separate observer-relative scene adapter and GPU depth-map renderer. Sample
loaded DEM; triangulate actual-height building footprints, roofs and facades with
Earcut. Render from the observer to a depth texture, then reconstruct visible map
surfaces from main-scene depth and compare against it inside the observer frustum.
Keep the independent geographic state separate from camera and measurement state.

Bound range, analysis count and geometry. Mark missing data and withhold green
classification rather than treating missing elevations as real flat ground/heights.
Document loaded-tile and sampling limitations explicitly in the UI/handoff.

## Alternatives

- A cone overlay or one target ray cannot classify surfaces throughout the volume.
- Per-pixel CPU raycasting on pointer movement would stall the UI on dense scenes.
- A second GIS engine/scene would duplicate resources and risk regressions in current
  picking, terrain and measurement rendering.
- A backend regional service could guarantee explicit coverage, but requires a new
  data/API effort beyond this frontend-only implementation. The scene adapter remains
  the replacement boundary for that future work.

## Consequences

Real-time edits and main-camera motion are decoupled. The renderer uses additional
bounded depth textures/mesh buffers and must recreate them after style removal.
Terrain sampling, shadow resolution and loaded geometry limit accuracy. Custom scene
objects need explicit picking/occluder adapters. No new backend service is deployed.
