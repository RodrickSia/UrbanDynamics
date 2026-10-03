import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { configureMapLibreWorker } from '../../src/features/map/config/maplibreWorker';
import { BUILDING_PAINT, BUILDINGS_LAYER_ID, setBuildings3d } from '../../src/features/map/layers/buildings3d';
import { getMapStyle } from '../../src/features/map/config/mapConfig';
import { createMeasurementLayer } from '../../src/features/map/layers/measurementLayer';
import { setTerrain } from '../../src/features/map/layers/terrain';
import { createMapInteractionHandlers } from '../../src/features/map/utils/mapInteractions';
import type { MeasurementState, MapMode } from '../../src/features/map/types/map';
import type { UrbanMapProps } from '../../src/features/map/components/UrbanMap.types';

configureMapLibreWorker(maplibregl);
const isLive = new URLSearchParams(location.search).has('live');
const isGoong = new URLSearchParams(location.search).has('goong');
const map = new maplibregl.Map({
  container: 'map', center: [106.7, 10.8], zoom: 17, pitch: 60,
  canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
  style: isGoong ? getMapStyle(import.meta.env.VITE_GOONG_MAPTILES_KEY) : { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#233440' } }] },
});
const layer = createMeasurementLayer(maplibregl.MercatorCoordinate);
let mode: MapMode = '3d';
let measurement: MeasurementState = { status: 'active', points: [], preview: null };
const sync = () => layer.setMeasurement(measurement, mode);
const props = () => ({
  mode, measurement,
  onMeasurementPoint: (point) => { measurement = { ...measurement, points: [...measurement.points, point], preview: null }; sync(); },
  onMeasurementPreview: (preview) => { measurement = { ...measurement, preview }; sync(); },
  onMeasurementPointsChange: (points) => { measurement = { ...measurement, points }; sync(); },
} as UrbanMapProps);
const handlers = createMapInteractionHandlers(map, props, layer.projection);
map.on('click', handlers.click);
map.on('mousemove', handlers.mousemove);
map.on('movestart', handlers.movestart);
map.on('idle', handlers.idle);

function project(lng: number, lat: number, elevation: number) {
  const p = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], elevation);
  const m = new DOMMatrix(layer.projection.matrix ?? undefined);
  const clip = m.transformPoint({ x: p.x, y: p.y, z: p.z });
  return { x: (clip.x / clip.w + 1) / 2 * map.getCanvas().clientWidth,
    y: (1 - clip.y / clip.w) / 2 * map.getCanvas().clientHeight };
}

// Only this dedicated test page exposes its map. The application has no test globals.
Object.assign(window, { harness: {
  map, project,
  state: () => structuredClone(measurement),
  reset: () => { measurement = { status: 'active', points: [], preview: null }; sync(); },
  done: () => { measurement = { ...measurement, status: 'complete', preview: null }; sync(); },
  markerError: (lng: number, lat: number, elevation: number) => {
    const p = project(lng, lat, elevation);
    const gl = map.getCanvas().getContext('webgl2')!;
    const data = new Uint8Array(25 * 25 * 4);
    const x0 = Math.round(p.x) - 12;
    const y0 = gl.drawingBufferHeight - Math.round(p.y) - 12;
    gl.readPixels(x0, y0, 25, 25, gl.RGBA, gl.UNSIGNED_BYTE, data);
    let nearest = Infinity;
    for (let y = 0; y < 25; y += 1) for (let x = 0; x < 25; x += 1) {
      const i = (y * 25 + x) * 4;
      if (data[i] > 225 && data[i + 1] > 225 && data[i + 2] > 225) nearest = Math.min(nearest, Math.hypot(x - 12, y - 12));
    }
    return nearest;
  },
  mode: (next: MapMode) => { mode = next; setTerrain(map, next === '3d'); map.jumpTo({ pitch: next === '3d' ? 60 : 0 }); sync(); },
  pixels: () => {
    const gl = map.getCanvas().getContext('webgl2')!;
    const pixels = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
    gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    let yellow = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i] > 220 && pixels[i + 1] > 130 && pixels[i + 1] < 205 && pixels[i + 2] < 65) yellow += 1;
    }
    return { yellow, error: gl.getError() };
  },
  laserPixels: () => {
    const gl = map.getCanvas().getContext('webgl2')!;
    const data = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
    gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, data);
    const coordinates: number[][] = [];
    for (let y = 0; y < gl.drawingBufferHeight; y++) for (let x = 0; x < gl.drawingBufferWidth; x++) {
      const i = (y * gl.drawingBufferWidth + x) * 4;
      if (data[i] > 200 && data[i+1] > 95 && data[i+1] < 205 && data[i+2] < 80) coordinates.push([x, gl.drawingBufferHeight - y - 1]);
    }
    return coordinates;
  },
} });

map.on('load', () => {
  setTerrain(map, true);
  if (isGoong) { map.jumpTo({ center: [106.703, 10.776], zoom: 17 }); setBuildings3d(map, true, 1); }
  if (!isLive && !isGoong) {
    map.addSource('test-buildings', { type: 'geojson', data: {
      type: 'FeatureCollection', features: [{ type: 'Feature', properties: { max_height: 80 }, geometry: {
        type: 'Polygon', coordinates: [[[106.6998, 10.7998], [106.7002, 10.7998], [106.7002, 10.8002], [106.6998, 10.8002], [106.6998, 10.7998]]],
      } }],
    } });
    map.addLayer({ id: BUILDINGS_LAYER_ID, type: 'fill-extrusion', source: 'test-buildings', paint: { ...BUILDING_PAINT, 'fill-extrusion-opacity': 1 } });
  }
  map.addLayer(layer);
  sync();
});
