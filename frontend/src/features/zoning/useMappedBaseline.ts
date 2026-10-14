import { useEffect, useRef } from 'react';
import type { Map as MapLibreMap, MapSourceDataEvent } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import type { ZoningBridge } from './types';
import { planBuildings } from './planBuildingGeometry';

const HEIGHT_KEYS = ['max_height', 'height', 'render_height', 'building:height', 'floors', 'building:levels', 'levels'];

/** Read original provider tiles in both 2D and 3D, never the proposed extrusions. */
export function useMappedBaseline(map: MapLibreMap | null, bridge: ZoningBridge) {
  const current = useRef(bridge.development?.onBaseline);
  useEffect(() => { current.current = bridge.development?.onBaseline; });
  const parcel = bridge.development?.parcel;
  const enabled = bridge.active && bridge.development?.active;
  useEffect(() => {
    if (!map || !enabled || !parcel) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let signature = '';
    const collect = () => {
      if (!map.getSource('composite')) return;
      const features = map.querySourceFeatures('composite', { sourceLayer: 'VN_Building' });
      const data = planBuildings(features, parcel.geometry, []);
      // Keep the existing API bounds; an incomplete tile inventory remains estimated.
      let vertices = 0;
      const bounded: FeatureCollection = { type: 'FeatureCollection', features: [] };
      for (const feature of data.features) {
        if (feature.geometry.type !== 'Polygon' && feature.geometry.type !== 'MultiPolygon') continue;
        const count = JSON.stringify(feature.geometry.coordinates).match(/\[/g)?.length ?? 0;
        if (count > 2000 || vertices + count > 20000 || bounded.features.length >= 200) continue;
        vertices += count;
        bounded.features.push({ ...feature, properties: Object.fromEntries(HEIGHT_KEYS.flatMap(key => {
          const value = feature.properties?.[key];
          return typeof value === 'number' || typeof value === 'string' ? [[key, value]] : [];
        })) });
      }
      const next = JSON.stringify(bounded);
      if (signature !== next) { signature = next; current.current?.(parcel.id, bounded); }
    };
    const schedule = () => { clearTimeout(timer); timer = setTimeout(collect, 200); };
    const loaded = (event: MapSourceDataEvent) => { if (event.sourceId === 'composite') schedule(); };
    collect();
    map.on('sourcedata', loaded); map.on('moveend', schedule); map.on('style.load', schedule);
    return () => { clearTimeout(timer); map.off('sourcedata', loaded); map.off('moveend', schedule); map.off('style.load', schedule); };
  }, [map, enabled, parcel]);
}
