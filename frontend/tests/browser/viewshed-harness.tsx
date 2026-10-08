import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import '../../src/styles.css';
import { useReducer, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { configureMapLibreWorker } from '../../src/features/map/config/maplibreWorker';
import { BUILDINGS_LAYER_ID, BUILDING_PAINT } from '../../src/features/map/layers/buildings3d';
import { createMeasurementLayer } from '../../src/features/map/layers/measurementLayer';
import { setTerrain } from '../../src/features/map/layers/terrain';
import { ViewshedScene } from '../../src/features/map/viewshed/ViewshedScene';
import { ViewshedPanel } from '../../src/features/map/viewshed/ViewshedPanel';
import { initialViewsheds, viewshedReducer } from '../../src/features/map/viewshed/state';

configureMapLibreWorker(maplibregl);
const map = new maplibregl.Map({
  container: 'map',
  center: [106.7, 10.8],
  zoom: 17,
  pitch: 50,
  canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
  style: {
    version: 8,
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#b5b5b5' } }],
  },
});
const measurement = createMeasurementLayer(maplibregl.MercatorCoordinate);
const install = () => {
  setTerrain(map, true);
  map.addSource('buildings', {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { max_height: 30 },
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [106.6998, 10.7999],
                [106.7002, 10.7999],
                [106.7002, 10.8001],
                [106.6998, 10.8001],
                [106.6998, 10.7999],
              ],
            ],
          },
        },
      ],
    },
  });
  map.addLayer({
    id: BUILDINGS_LAYER_ID,
    type: 'fill-extrusion',
    source: 'buildings',
    paint: { ...BUILDING_PAINT, 'fill-extrusion-opacity': 0.8 },
  });
  map.addLayer(measurement);
};
map.on('style.load', install);
const project = (lng: number, lat: number, z: number) => {
  const p = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], z);
  return measurement.projection.project(
    [p.x, p.y, p.z],
    map.getCanvas().clientWidth,
    map.getCanvas().clientHeight,
  );
};
const pixel = (lng: number, lat: number, z: number) => {
  const p = project(lng, lat, z)!;
  const gl = map.getCanvas().getContext('webgl2')!;
  const out = new Uint8Array(4);
  // MapLibre may leave an offscreen read target bound after terrain rendering.
  // Assert the displayed canvas, not whichever FBO its last pass used.
  const read=gl.getParameter(gl.READ_FRAMEBUFFER_BINDING);
  gl.bindFramebuffer(gl.READ_FRAMEBUFFER,null);
  gl.readPixels(
    Math.round(p.x),
    gl.drawingBufferHeight - Math.round(p.y) - 1,
    1,
    1,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    out,
  );
  gl.bindFramebuffer(gl.READ_FRAMEBUFFER,read);
  return Array.from(out);
};
export function Harness() {
  const [state, onAction] = useReducer(viewshedReducer, initialViewsheds),
    [status, onStatus] = useState('');
  const [mode, setMode] = useState<'2d' | '3d'>('3d');
  // Only the isolated test fixture exposes internals; production has no globals.
  Object.assign(window, {
    viewshedHarness: {
      map,
      state,
      status,
      onAction,
      project,
      pixel,
      glError: () => map.getCanvas().getContext('webgl2')!.getError(),
      mode: (next: '2d' | '3d') => {
        setTerrain(map, next === '3d');
        setMode(next);
      },
      reload: () =>
        map.setStyle(
          {
            version: 8,
            sources: {},
            layers: [
              { id: 'background', type: 'background', paint: { 'background-color': '#b5b5b5' } },
            ],
          },
          { diff: false },
        ),
    },
  });
  return (
    <>
      <ViewshedScene
        map={map}
        projection={measurement.projection}
        mode={mode}
        bridge={{ state, onAction, onStatus }}
      />
      {state.phase !== 'idle' && (
        <ViewshedPanel state={state} onAction={onAction} status={status} />
      )}
    </>
  );
}
map.once('load', () => createRoot(document.getElementById('ui')!).render(<Harness />));
