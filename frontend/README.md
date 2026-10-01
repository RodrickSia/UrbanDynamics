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
```

The application opens in 2D at a nationwide Vietnam view. Search and place details use the left edge, data layers use a full-height drawer on the right, and polygon drawing uses a compact bottom-center toolbar. The interface uses light glass surfaces. GSAP animates panel entrances, lifts the 2D/3D text into view, and provides tool hover feedback while respecting reduced-motion preferences.

## Current integration status

- Goong standard and satellite basemaps use `VITE_GOONG_MAPTILES_KEY`; satellite is rendered as a raster-only style so baked imagery labels are not duplicated by vector symbols.
- The MapLibre worker is emitted by Vite from a local module URL, avoiding worker-loading failures caused by an unresolved default URL.
- 3D buildings are added only when the active Goong style exposes `composite / VN_Building`; missing sources degrade gracefully.
- Terrain uses Goong DEM after the style is ready and is removed when returning to 2D.
- User and selected-place markers are rendered only after geolocation succeeds or a place/map selection is made. Empty-map clicks toggle generic place details; named POIs always open or update the drawer.
- Population, public facilities, traffic, rain, flood, planning, land price, road density, and green-area layers are disabled UI integration points. No synthetic urban data is shown.
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
- `@turf/area` and `@turf/bbox`: polygon measurements.
- `lucide-react`: interface icons.
- `gsap` and `@gsap/react`: scoped panel and mode transitions with automatic React cleanup.

Runtime dependencies belong in `frontend/package.json`; the repository root intentionally has no npm manifest.
