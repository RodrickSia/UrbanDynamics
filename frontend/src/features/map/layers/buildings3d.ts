import type { FillExtrusionLayerSpecification, Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';
import { API_BASE_URL } from '../../../services/api';

export const BUILDINGS_LAYER_ID = 'urban-buildings-3d';
export const BUILDINGS_SOURCE_ID = 'urban-gba-lod1';
export const BUILDINGS_SNAPSHOT_URL = `${API_BASE_URL}/api/v1/buildings/snapshot`;
export const BUILDING_PAINT: FillExtrusionLayerSpecification['paint'] = {
  'fill-extrusion-color': '#a9b6ae',
  'fill-extrusion-height': ['to-number', ['get', 'height_m'], 0],
  'fill-extrusion-base': 0,
};

function firstLabelLayer(style: StyleSpecification): string | undefined {
  return style.layers?.find(
    (layer) => layer.type === 'symbol' && Boolean(layer.layout?.['text-field']),
  )?.id;
}

export function setBuildings3d(map: MapLibreMap, enabled: boolean, opacity = 0.8): boolean {
  // Never display Goong's extrusions alongside the warehouse GBA model.
  const style = map.getStyle();
  for (const layer of style.layers ?? []) {
    if (layer.type === 'fill-extrusion' && layer.id !== BUILDINGS_LAYER_ID
      && layer.source === 'composite' && layer['source-layer'] === 'VN_Building') {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }
  if (!enabled) {
    if (map.getLayer(BUILDINGS_LAYER_ID)) map.removeLayer(BUILDINGS_LAYER_ID);
    if (map.getSource(BUILDINGS_SOURCE_ID)) map.removeSource(BUILDINGS_SOURCE_ID);
    return true;
  }

  if (map.getLayer(BUILDINGS_LAYER_ID)) {
    map.setPaintProperty(BUILDINGS_LAYER_ID, 'fill-extrusion-opacity', opacity);
    map.moveLayer(BUILDINGS_LAYER_ID, firstLabelLayer(map.getStyle()));
    return true;
  }
  if (!map.getSource(BUILDINGS_SOURCE_ID)) {
    map.addSource(BUILDINGS_SOURCE_ID, {
      type: 'vector',
      tiles: [`${API_BASE_URL}/api/v1/buildings/tiles/{z}/{x}/{y}.pbf`],
      minzoom: 14,
      maxzoom: 16,
      attribution: 'GlobalBuildingAtlas LoD1 · CC BY-NC 4.0 · UrbanDynamics',
    });
  }

  map.addLayer(
    {
      id: BUILDINGS_LAYER_ID,
      source: BUILDINGS_SOURCE_ID,
      'source-layer': 'buildings',
      type: 'fill-extrusion',
      minzoom: 14,
      paint: {
        ...BUILDING_PAINT,
        'fill-extrusion-opacity': opacity,
      },
    },
    firstLabelLayer(style),
  );
  return true;
}
