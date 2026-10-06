# UrbanDynamics frontend

React, TypeScript, Vite, MapLibre, and GSAP power the national urban-intelligence map workspace.

## Local setup

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Set the frontend map-rendering credential in `frontend/.env.local`:

```dotenv
VITE_GOONG_MAPTILES_KEY=<your frontend map tiles key>
```

Only the Goong **Map Tiles Key** belongs in the frontend. Never add a Goong REST API key to frontend source, fixtures, Docker configuration, or Vite environment variables. Autocomplete and geocoding will be called through the UrbanDynamics backend when those endpoints are available.

## Commands

```bash
npm run dev
npm run build
npm run lint
npm test
npx playwright install chromium
npm run test:map
# Optional: requires network access and the configured Goong Map Tiles Key
npm run test:map:live
```

The application opens in 2D at a nationwide Vietnam view. Search and place details use the left edge, data layers use a full-height drawer on the right, and distance measurement uses a compact bottom-center toolbar. The interface uses light glass surfaces. GSAP animates panel entrances, lifts the 2D/3D text into view, and provides tool hover feedback while respecting reduced-motion preferences.

## Current integration status

- Goong standard and satellite basemaps use `VITE_GOONG_MAPTILES_KEY`; satellite is rendered as a raster-only style so baked imagery labels are not duplicated by vector symbols.
- The MapLibre worker is emitted by Vite from a local module URL, avoiding worker-loading failures caused by an unresolved default URL.
- 3D buildings are added only when the active Goong style exposes `composite / VN_Building`; missing sources degrade gracefully. The native Goong extrusion is hidden to avoid duplicate geometry. Rendering and measurement both recognize Goong `max_height` (with `min_height` for raised facades).
- Terrain uses Mapterhorn Terrarium DEM tiles (512 px), capped at source zoom 12 for Vietnam's global coverage and overzoomed for street views. Elevation exaggeration stays at 1. Terrain and hillshade use separate sources. It is attached after the style is ready and removed when returning to 2D.
- Multi-point measurements persist across camera/mode changes. 3D snaps to visible vertices (8 CSS px), edges (6 CSS px), faces and terrain. Edge hover highlights the full underlying edge before the first click, without a fake measurement. Each committed point stores world coordinates and snap topology. Same-edge, vertical and level measurements use one direct orange/white line and a camera-facing dark pill. Metres display two decimals; source accuracy is still limited by building/DEM data. Unknown heights report `Elevation unavailable`.
- `Components` is opt-in: only unrelated 3D endpoints with both nonzero horizontal and vertical differences get secondary H/ΔZ lines and labels. The amber horizontal laser is an independent height-reference contour: it follows the pointer during active 3D measurement with valid elevation, including before the first click and when snapping, regardless of `Components`. It disappears on Done, leaving the map, 2D, or unavailable elevation. The reusable depth texture samples visible terrain/building surfaces without recreating the scene; it does not fill coplanar surfaces or draw through empty space.
- Picking rejects occluded geometry. Surface/snap topology and camera inverses are cached; committed coordinates never change with zoom. Current support covers Goong extrusions and terrain; no custom 3D object source exists in this repo. Custom meshes will require a picking adapter. Stable backend building IDs and unclipped geometry are needed for topology identity across all tile boundaries/LODs.
- Roof/facade selection uses a terrain-aware camera ray. Acquired world coordinates and elevations are frozen; GPU vertices are relative to a local origin to prevent high-zoom float32 drift.
- Browser regression tests exercise real MapLibre/WebGL with controlled DEM/building fixtures, check yellow pixels and marker positions after camera changes, and test roof/facade hits. Separate live tests verify Mapterhorn coverage and the configured Goong application. Fixture pages are development-only and are not included in production output.
- User and selected-place markers are rendered only after geolocation succeeds or a place/map selection is made. Empty-map clicks toggle generic place details; named POIs always open or update the drawer.
- The official An Khánh land-price layer is served by the backend's PostGIS vector tiles. Enable it, zoom in, and click a road line to inspect its official price values and geometry-coverage note.
- Population, public facilities, traffic, rain, flood, planning, road density, and green-area layers remain disabled UI integration points. No synthetic urban data is shown.
- Search history is local, and area/weather values remain local placeholders until backend integration. Future implementations call the UrbanDynamics backend through `VITE_API_BASE_URL`; they must not call credentialed Goong REST APIs directly.
- Backend engineers should use [`docs/frontend-backend-handoff.md`](../docs/frontend-backend-handoff.md) as the integration contract and implementation checklist.

## Container build

From the repository root, copy `.env.example` to `.env`, set `VITE_GOONG_MAPTILES_KEY`, then run:

```bash
docker compose up --build
```

Vite embeds public frontend variables at build time. Treat the Map Tiles Key as browser-visible and configure its allowed origins in Goong; keep all server-side credentials in the backend.

## Runtime dependencies

- `react` and `react-dom`: component runtime.
- `maplibre-gl`: map rendering.
- `lucide-react`: interface icons.
- `gsap` and `@gsap/react`: scoped panel and mode transitions with automatic React cleanup.

Runtime dependencies belong in `frontend/package.json`; the repository root intentionally has no npm manifest.
