import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import '../../src/styles.css';
import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { UrbanMap } from '../../src/features/map/components/UrbanMap';
import type { MapMode, MeasurementState } from '../../src/features/map/types/map';
import type { MapStyleId } from '../../src/features/map/config/mapConfig';
import type { MeasurementLayer } from '../../src/features/map/layers/measurementLayer';

const configuration = { ok: true as const, mapKey: 'fixture', styleUrl: '' };
const noop = () => undefined;
const captured: { map?: maplibregl.Map } = {};
let cameraAnimations = 0;
const addControl = maplibregl.Map.prototype.addControl;
maplibregl.Map.prototype.addControl = function (...args) {
  captured.map = this;
  return addControl.apply(this, args);
};
const easeTo = maplibregl.Map.prototype.easeTo;
maplibregl.Map.prototype.easeTo = function (...args) {
  cameraAnimations++;
  return easeTo.apply(this, args);
};

export function Fixture() {
  const [mode, setMode] = useState<MapMode>('2d');
  const [style, setStyle] = useState<MapStyleId>('standard');
  const [opacity, setOpacity] = useState(1);
  const [measurement, setMeasurement] = useState<MeasurementState>({ status: 'active', points: [], preview: null });
  Object.assign(window, { workspace: {
    map: () => captured.map, mode: setMode, style: setStyle, opacity: setOpacity,
    state: () => measurement, animations: () => cameraAnimations,
    measurement: setMeasurement,
    project: (lng: number, lat: number, altitude: number) => {
      const map = captured.map!;
      const custom = map.getLayer('urban-distance-measurement') as unknown as { implementation: MeasurementLayer };
      const p = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], altitude);
      return custom.implementation.projection.project([p.x, p.y, p.z], map.getCanvas().clientWidth, map.getCanvas().clientHeight);
    },
  } });
  return <UrbanMap configuration={configuration} mapStyle={style} mode={mode}
    buildingsEnabled buildingsOpacity={opacity} measurement={measurement}
    selection={null} userLocation={null} focusRequest={null} controlRequest={null}
    onMeasurementPoint={point => setMeasurement(value => ({ ...value, points: [...value.points, point], preview: null }))}
    onMeasurementPreview={preview => setMeasurement(value => ({ ...value, preview }))}
    onMeasurementPointsChange={points => setMeasurement(value => ({ ...value, points }))}
    onPointSelect={noop} onUserLocationChange={noop} onStatusChange={noop} onBuildingsAvailabilityChange={noop} />;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
