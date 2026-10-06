import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import type { MeasurementProjection } from '../utils/measurementProjection';
import { resolveMeasurementPoint } from '../utils/measurementElevation';
import { MEASUREMENT_LAYER_ID } from '../layers/measurementLayer';
import type { MapMode } from '../types/map';
import { createViewshedLayer, VIEWSHED_LAYER_ID, type ViewshedLayer } from './layer';
import type { ViewshedAction, ViewshedState } from './state';
import { ViewshedHandles } from './ViewshedHandles';

export interface ViewshedBridge {
  state: ViewshedState;
  onAction: (action: ViewshedAction) => void;
  onStatus: (message: string) => void;
}
export function ViewshedScene({
  map,
  projection,
  mode,
  bridge,
}: {
  map: MapLibreMap | null;
  projection: MeasurementProjection | null;
  mode: MapMode;
  bridge: ViewshedBridge;
}) {
  const current = useRef({ bridge, mode });
  useEffect(() => {
    current.current = { bridge, mode };
  }, [bridge, mode]);
  const layer = useRef<ViewshedLayer | null>(null);
  useEffect(() => {
    if (!map || !projection) return;
    let dirty = true,
      raf = 0;
    const renderer = createViewshedLayer((message) => current.current.bridge.onStatus(message));
    layer.current = renderer;
    const ensureOrder = () => {
      const layers = map.getStyle()?.layers ?? [];
      const index = layers.findIndex((item) => item.id === VIEWSHED_LAYER_ID);
      const measurementIndex = layers.findIndex((item) => item.id === MEASUREMENT_LAYER_ID);
      if (
        index >= 0 &&
        index !== (measurementIndex >= 0 ? measurementIndex - 1 : layers.length - 1)
      ) {
        map.moveLayer(VIEWSHED_LAYER_ID, measurementIndex >= 0 ? MEASUREMENT_LAYER_ID : undefined);
      }
    };
    const attach = () => {
      if (!map.getLayer(VIEWSHED_LAYER_ID))
        map.addLayer(
          renderer,
          map.getLayer(MEASUREMENT_LAYER_ID) ? MEASUREMENT_LAYER_ID : undefined,
        );
      ensureOrder();
      renderer.update(current.current.bridge.state.items, current.current.mode === '3d');
      renderer.invalidate();
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach);
    const scenechange = () => {
      dirty = true;
      ensureOrder();
    };
    const idle = () => {
      if (dirty) {
        dirty = false;
        renderer.invalidate();
      }
    };
    map.on('sourcedata', scenechange);
    map.on('styledata', scenechange);
    map.on('idle', idle);
    const pick = (e: MapMouseEvent) => {
      const point = resolveMeasurementPoint(
        map,
        e.lngLat.lng,
        e.lngLat.lat,
        '3d',
        e.point,
        undefined,
        projection,
      );
      if (!point?.elevationAvailable) {
        current.current.bridge.onStatus('Elevation unavailable · choose a loaded surface');
        return null;
      }
      return {
        longitude: point.longitude,
        latitude: point.latitude,
        elevationMeters: point.elevationMeters,
      };
    };
    const click = (e: MapMouseEvent) => {
      const { state, onAction } = current.current.bridge;
      if (current.current.mode !== '3d' || !['observer', 'target'].includes(state.phase)) return;
      const point = pick(e);
      if (!point) return;
      if (state.phase === 'observer') point.elevationMeters += 1.7;
      onAction({ type: 'place', point, id: crypto.randomUUID() });
    };
    const move = (e: MapMouseEvent) => {
      if (
        current.current.mode !== '3d' ||
        current.current.bridge.state.phase !== 'target' ||
        map.isMoving()
      )
        return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (current.current.bridge.state.phase !== 'target' || map.isMoving()) return;
        const point = pick(e);
        if (point) current.current.bridge.onAction({ type: 'preview', point });
      });
    };
    map.on('click', click);
    map.on('mousemove', move);
    return () => {
      cancelAnimationFrame(raf);
      map.off('click', click);
      map.off('mousemove', move);
      map.off('style.load', attach);
      map.off('sourcedata', scenechange);
      map.off('styledata', scenechange);
      map.off('idle', idle);
      if (map.getLayer(VIEWSHED_LAYER_ID)) map.removeLayer(VIEWSHED_LAYER_ID);
      layer.current = null;
    };
  }, [map, projection]);
  useEffect(() => {
    layer.current?.update(bridge.state.items, mode === '3d');
    map
      ?.getCanvas()
      .classList.toggle(
        'is-viewshed-placing',
        mode === '3d' && ['observer', 'target'].includes(bridge.state.phase),
      );
    return () => {
      map?.getCanvas().classList.remove('is-viewshed-placing');
    };
  }, [bridge.state, mode, map]);
  return map && projection && mode === '3d' ? (
    <ViewshedHandles
      map={map}
      projection={projection}
      state={bridge.state}
      onAction={bridge.onAction}
    />
  ) : null;
}
