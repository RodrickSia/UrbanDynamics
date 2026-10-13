import { useEffect, useRef } from 'react';
import { developmentData } from './developmentSceneData';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import type { ZoningBridge } from './types';
import { installDemolition } from './demolition';

const SOURCE = 'development-scene';
export const BUILDING_LAYER = 'development-buildings';
const OUTLINE = 'development-outlines', SELECTION = 'development-selection';
export function DevelopmentScene({ map, bridge }: { map: MapLibreMap | null; bridge: ZoningBridge }) {
  const current = useRef(bridge);
  useEffect(() => { current.current = bridge; }, [bridge]);
  useEffect(() => {
    if (!map || !bridge.active) return;
    const attach = () => {
      const installing = !map.getLayer(BUILDING_LAYER);
      if (!map.getSource(SOURCE)) map.addSource(SOURCE, { type: 'geojson', data: developmentData(current.current) });
      if (!map.getLayer(SELECTION)) map.addLayer({ id: SELECTION, source: SOURCE, type: 'fill', filter: ['==', 'kind', 'parcel'],
        paint: { 'fill-color': '#2877dc', 'fill-opacity': .07 } });
      if (!map.getLayer(BUILDING_LAYER)) map.addLayer({ id: BUILDING_LAYER, source: SOURCE, type: 'fill-extrusion', filter: ['==', 'kind', 'building'],
        paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'height'],
          'fill-extrusion-base': 0, 'fill-extrusion-opacity': .85 } });
      if (!map.getLayer(OUTLINE)) map.addLayer({ id: OUTLINE, source: SOURCE, type: 'line',
        paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-opacity': .9 } });
      // Keep edit handles pickable above the new scene.
      if (installing) for (const id of ['zoning-outline', 'zoning-vertices', 'zoning-snap-indicator']) if (map.getLayer(id)) map.moveLayer(id);
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach); map.on('idle', attach);
    return () => {
      map.off('style.load', attach); map.off('idle', attach);
      for (const id of [OUTLINE, BUILDING_LAYER, SELECTION]) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
    };
  }, [map, bridge.active]);
  useEffect(() => { (map?.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(developmentData(bridge)); }, [map, bridge]);
  const masks = bridge.active ? bridge.scenario?.demolition_masks : undefined;
  useEffect(() => {
    if (map && masks?.length) return installDemolition(map, masks.map(m => m.geometry));
  }, [map, masks]);
  return null;
}

