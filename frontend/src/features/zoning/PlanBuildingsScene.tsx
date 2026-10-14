import { useEffect, useRef } from 'react';
import type { GeoJSONSource, Map as MapLibreMap, MapSourceDataEvent, TransitionSpecification } from 'maplibre-gl';
import { planBuildings } from './planBuildingGeometry';
import { watchBuildingUpdates } from '../map/layers/buildingUpdates';
import type { ZoningBridge } from './types';

/** Display-only clipping. Provider source geometry and paints remain unchanged. */
export function PlanBuildingsScene({ map, bridge, mode }: {
  map: MapLibreMap | null; bridge: ZoningBridge; mode: '2d' | '3d';
}) {
  const study = bridge.active ? (bridge.analysis?.active ? bridge.analysis.geometry ?? undefined : bridge.plan?.study_area) : undefined;
  const masks = bridge.scenario?.demolition_masks;
  const enabled = !!study;
  const current = useRef({ study, masks, mode });
  const update = useRef<(geometryChanged: boolean) => void>(() => {});
  useEffect(() => {
    const geometryChanged = study !== current.current.study || masks !== current.current.masks;
    current.current = { study, masks, mode };
    update.current(geometryChanged);
  }, [study, masks, mode]);
  useEffect(() => {
    if (!map || !enabled) return;
    const originals = new Map<string, { layer: unknown; opacity: number; transition: TransitionSpecification | undefined }>();
    const owned = new Set<string>();
    const dirty = new Set<string>();
    const rendered = new Map<string, string>();
    let frame = 0, disposed = false, refreshing = false;
    const refresh = () => {
      frame = 0;
      const { study, masks, mode } = current.current;
      if (disposed || refreshing || !study || !map.getStyle()) return;
      refreshing = true;
      try {
      const targets = new Set([...originals.keys(), ...map.getStyle().layers.filter(layer =>
        layer.type === 'fill-extrusion' && !layer.id.startsWith('development-') && !layer.id.startsWith('indicator-chart-') && !layer.id.startsWith('plan-scope-')).map(layer => layer.id)]);
      for (const id of targets) {
        const sourceId = `plan-scope-${id}`, layer = map.getLayer(id);
        const spec = map.getStyle().layers.find(item => item.id === id);
        if (!layer || spec?.type !== 'fill-extrusion') {
          if (map.getLayer(sourceId)) map.removeLayer(sourceId);
          originals.delete(id);
          continue;
        }
        const opacity = map.getPaintProperty(id, 'fill-extrusion-opacity') as number | undefined;
        if (originals.get(id)?.layer !== layer) {
          originals.set(id, { layer, opacity: opacity ?? 1,
            transition: map.getPaintProperty(id, 'fill-extrusion-opacity-transition') }); dirty.add(id);
          map.setPaintProperty(id, 'fill-extrusion-opacity-transition', { duration: 0, delay: 0 });
        } else if (opacity !== 0) originals.get(id)!.opacity = opacity ?? 1;
        if (!map.getSource(sourceId)) {
          const data = planBuildings(map.querySourceFeatures(spec.source, { sourceLayer: spec['source-layer'] }), study, masks?.map(m => m.geometry) ?? []);
          map.addSource(sourceId, { type: 'geojson', data, maxzoom: 18 });
          owned.add(id);
          rendered.set(id, JSON.stringify(data));
          dirty.add(id);
        }
        if (!map.getLayer(sourceId)) {
          map.addLayer({ id: sourceId, type: 'fill-extrusion', source: sourceId,
            ...(spec.minzoom === undefined ? {} : { minzoom: spec.minzoom }),
            ...(spec.maxzoom === undefined ? {} : { maxzoom: spec.maxzoom }),
            ...(spec.filter === undefined ? {} : { filter: spec.filter }),
            layout: { ...spec.layout, visibility: mode === '3d' ? spec.layout?.visibility ?? 'visible' : 'none' },
            paint: { ...spec.paint, 'fill-extrusion-opacity': originals.get(id)!.opacity,
              'fill-extrusion-opacity-transition': { duration: 0, delay: 0 } } }, id);
        }
        const visibility = mode === '3d' ? spec.layout?.visibility ?? 'visible' : 'none';
        if (map.getLayoutProperty(sourceId, 'visibility') !== visibility) map.setLayoutProperty(sourceId, 'visibility', visibility);
        const targetOpacity = originals.get(id)!.opacity;
        if (map.getPaintProperty(sourceId, 'fill-extrusion-opacity') !== targetOpacity)
          map.setPaintProperty(sourceId, 'fill-extrusion-opacity', targetOpacity);
        // Opacity zero keeps original vector tiles loaded for the clipped display.
        if (opacity !== 0) map.setPaintProperty(id, 'fill-extrusion-opacity', 0);
        if (dirty.delete(id)) {
          const features = map.querySourceFeatures(spec.source, { sourceLayer: spec['source-layer'] });
          const data = planBuildings(features, study, masks?.map(m => m.geometry) ?? []);
          const signature = JSON.stringify(data);
          if (rendered.get(id) !== signature) {
            rendered.set(id, signature);
            (map.getSource(sourceId) as GeoJSONSource).setData(data);
          }
        }
      }
      } finally { refreshing = false; }
    };
    const schedule = () => { if (!disposed && !frame) frame = requestAnimationFrame(refresh); };
    const loaded = (event: MapSourceDataEvent) => {
      // Vector tile completion has a coord but no sourceDataType. Include it so
      // newly streamed buildings appear after panning and basemap reloads.
      if (event.sourceDataType !== 'content' && !event.coord) return;
      for (const id of originals.keys()) {
        const layer = map.getLayer(id);
        if (layer && 'source' in layer && layer.source === event.sourceId) dirty.add(id);
      }
      if (dirty.size) schedule();
    };
    const moved = () => { originals.forEach((_, id) => dirty.add(id)); schedule(); };
    update.current = geometryChanged => { if (geometryChanged) moved(); else refresh(); };
    const unwatch = watchBuildingUpdates(map, refresh);
    refresh();
    // Also discover layers supplied by a newly loaded basemap style.
    map.on('styledata', refresh); map.on('sourcedata', loaded); map.on('moveend', moved);
    return () => {
      disposed = true; cancelAnimationFrame(frame);
      unwatch();
      update.current = () => {};
      map.off('styledata', refresh); map.off('sourcedata', loaded); map.off('moveend', moved);
      for (const id of owned) {
        const sourceId = `plan-scope-${id}`;
        if (map.getLayer(sourceId)) map.removeLayer(sourceId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
        const original = originals.get(id);
        if (original && map.getLayer(id) === original.layer) {
          map.setPaintProperty(id, 'fill-extrusion-opacity', original.opacity);
          map.setPaintProperty(id, 'fill-extrusion-opacity-transition', original.transition);
        }
      }
    };
  }, [map, enabled]);
  return null;
}
