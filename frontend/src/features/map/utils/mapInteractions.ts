import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';

import type { UrbanMapProps } from '../components/UrbanMap.types';
import { MEASUREMENT_LAYER_ID } from '../layers/measurementLayer';
import {
  measurementPointsEqual,
  invalidateMeasurementPicking,
  refreshMeasurementPointElevation,
  resolveMeasurementPoint,
} from './measurementElevation';
import type { MeasurementProjection } from './measurementProjection';

export function createMapInteractionHandlers(
  map: MapLibreMap,
  getCurrent: () => UrbanMapProps,
  projection?: MeasurementProjection,
) {
  let previewFrame = 0;

  return {
    click(event: MapMouseEvent) {
      const current = getCurrent();
      if (current.measurement.status === 'active') {
        cancelAnimationFrame(previewFrame);
        current.onMeasurementPoint(resolveMeasurementPoint(
          map,
          event.lngLat.lng,
          event.lngLat.lat,
          current.mode,
          event.point,
          undefined,
          projection,
        ));
        return;
      }
      const visibleFeatures = map
        .queryRenderedFeatures(event.point)
        .filter((feature) => feature.layer.id !== MEASUREMENT_LAYER_ID)
        .slice(0, 5)
        .map((feature, index) => {
          const featureName = feature.properties?.name;
          const isNamedPlace = typeof featureName === 'string' && featureName.trim().length > 0;
          return {
            id: String(feature.id ?? `${feature.layer.id}-${index}`),
            label: String(featureName ?? feature.properties?.class ?? feature.layer.id),
            layer: feature.layer.id,
            isNamedPlace,
          };
        });
      current.onPointSelect({
        kind: 'point',
        longitude: event.lngLat.lng,
        latitude: event.lngLat.lat,
        zoom: map.getZoom(),
        features: visibleFeatures,
      });
    },
    mousemove(event: MapMouseEvent) {
      const current = getCurrent();
      if (current.measurement.status !== 'active' || map.isMoving()) return;
      cancelAnimationFrame(previewFrame);
      previewFrame = requestAnimationFrame(() => {
        const latest = getCurrent();
        if (latest.measurement.status !== 'active' || map.isMoving()) return;
        latest.onMeasurementPreview(resolveMeasurementPoint(
          map,
          event.lngLat.lng,
          event.lngLat.lat,
          latest.mode,
          event.point,
          'measurement-preview',
          projection,
        ));
      });
    },
    mouseout() {
      cancelAnimationFrame(previewFrame);
      getCurrent().onMeasurementPreview(null);
    },
    movestart() {
      invalidateMeasurementPicking(map);
      cancelAnimationFrame(previewFrame);
      getCurrent().onMeasurementPreview(null);
    },
    idle() {
      invalidateMeasurementPicking(map);
      const current = getCurrent();
      if (current.mode !== '3d' || current.measurement.points.length === 0) return;
      const points = current.measurement.points.map((point) => (
        refreshMeasurementPointElevation(map, point)
      ));
      if (!measurementPointsEqual(points, current.measurement.points)) {
        current.onMeasurementPointsChange(points);
      }
    },
    dispose() {
      cancelAnimationFrame(previewFrame);
    },
  };
}
