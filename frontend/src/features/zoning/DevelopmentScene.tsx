import { useEffect, useRef } from 'react';
import { developmentData } from './developmentSceneData';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import type { ZoningBridge } from './types';
import { installDemolition } from './demolition';

const SOURCE = 'development-scene';
export const BUILDING_LAYER = 'development-buildings';
export const BUILDING_EXCLUDED_LAYER = 'development-excluded-floors';
export const BUILDING_FOOTPRINT_LAYER = 'development-building-footprints';
const OUTLINE = 'development-outlines', SELECTION = 'development-selection';
export function DevelopmentScene({ map, bridge, mode }: { map: MapLibreMap | null; bridge: ZoningBridge; mode: '2d' | '3d' }) {
  const current = useRef(bridge);
  const currentMode = useRef(mode);
  useEffect(() => { current.current = bridge; currentMode.current = mode; }, [bridge, mode]);
  useEffect(() => {
    if (!map || !bridge.active) return;
    const attach = () => {
      const installing = !map.getLayer(BUILDING_LAYER);
      if (!map.getSource(SOURCE)) map.addSource(SOURCE, { type: 'geojson', data: developmentData(current.current) });
      if (!map.getLayer(SELECTION)) map.addLayer({ id: SELECTION, source: SOURCE, type: 'fill', filter: ['==', 'kind', 'parcel'],
        paint: { 'fill-color': '#2877dc', 'fill-opacity': .07 } });
      for (const [id, opacity] of [[BUILDING_LAYER, .85], [BUILDING_EXCLUDED_LAYER, .4]] as const)
        if (!map.getLayer(id)) map.addLayer({ id, source: SOURCE, type: 'fill-extrusion',
        filter: ['all', ['==', 'kind', 'building'], ['==', 'opacity', opacity]],
        layout: { visibility: currentMode.current === '3d' ? 'visible' : 'none' },
        paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'height'],
          'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-opacity': opacity } });
      if (!map.getLayer(BUILDING_FOOTPRINT_LAYER)) map.addLayer({ id: BUILDING_FOOTPRINT_LAYER, source: SOURCE, type: 'fill', filter: ['all', ['==', 'kind', 'building'], ['==', 'base', 0]],
        layout: { visibility: currentMode.current === '2d' ? 'visible' : 'none' },
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': .35 } });
      if (!map.getLayer(OUTLINE)) map.addLayer({ id: OUTLINE, source: SOURCE, type: 'line',
        filter: ['any', ['!=', 'kind', 'building'], ['==', 'base', 0]],
        paint: { 'line-color': ['coalesce', ['get', 'outline'], ['get', 'color']], 'line-width': 2, 'line-opacity': .9 } });
      // Keep edit handles pickable above the new scene.
      if (installing) for (const id of ['zoning-outline', 'zoning-vertices', 'zoning-snap-indicator']) if (map.getLayer(id)) map.moveLayer(id);
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach); map.on('idle', attach);
    return () => {
      map.off('style.load', attach); map.off('idle', attach);
      for (const id of [OUTLINE, BUILDING_FOOTPRINT_LAYER, BUILDING_EXCLUDED_LAYER, BUILDING_LAYER, SELECTION]) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
    };
  }, [map, bridge.active]);
  useEffect(() => {
    // Keep the source and editor selection alive across camera changes.
    for (const id of [BUILDING_LAYER, BUILDING_EXCLUDED_LAYER, BUILDING_FOOTPRINT_LAYER]) {
      if (!map?.getLayer(id)) continue;
      const visible = id === BUILDING_FOOTPRINT_LAYER ? mode === '2d' : mode === '3d';
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }
  }, [map, bridge.active, mode]);
  useEffect(() => { (map?.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(developmentData(bridge)); }, [map, bridge]);
  const masks = bridge.active ? bridge.scenario?.demolition_masks : undefined;
  useEffect(() => {
    if (map && masks?.length) return installDemolition(map, masks.map(m => m.geometry));
  }, [map, masks]);
  return null;
}

