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
  let sceneNeedsSettlement = true;
  let committedPointer: { x: number; y: number; pointId: string } | null = null;

  return {
    click(event: MapMouseEvent) {
      const current = getCurrent();
      if (current.measurement.status === 'active') {
        cancelAnimationFrame(previewFrame);
        const point = resolveMeasurementPoint(
          map,
          event.lngLat.lng,
          event.lngLat.lat,
          current.mode,
          event.point,
          undefined,
          projection,
        );
        if (point) {
          committedPointer = { x: event.point.x, y: event.point.y, pointId: point.id };
          current.onMeasurementPoint(point);
        }
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
        // Mousemove can fire immediately after click (including device jitter).
        // Keep the committed white anchor instead of recreating a red preview
        // on top of it; meaningful movement still starts the next segment.
        if (committedPointer && latest.measurement.points.at(-1)?.id === committedPointer.pointId
          && Math.hypot(event.point.x - committedPointer.x, event.point.y - committedPointer.y) <= 3) {
          latest.onMeasurementPreview(null);
          return;
        }
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
      sceneNeedsSettlement = true;
      committedPointer = null;
      invalidateMeasurementPicking(map);
      cancelAnimationFrame(previewFrame);
      getCurrent().onMeasurementPreview(null);
    },
    idle() {
      // Source events can precede the GPU's final tile/terrain render. Retire
      // that intermediate snapshot once the scene settles, not every frame.
      if (sceneNeedsSettlement) {
        invalidateMeasurementPicking(map);
        sceneNeedsSettlement = false;
      }
      const current = getCurrent();
      if (current.mode !== '3d' || current.measurement.points.length === 0) return;
      const points = current.measurement.points.map((point) => (
        refreshMeasurementPointElevation(map, point)
      ));
      if (!measurementPointsEqual(points, current.measurement.points)) {
        current.onMeasurementPointsChange(points);
      }
    },
    scenechange() {
      sceneNeedsSettlement = true;
      invalidateMeasurementPicking(map);
    },
    dispose() {
      cancelAnimationFrame(previewFrame);
    },
  };
}
