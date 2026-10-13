import type { FillExtrusionLayerSpecification, Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';

export const BUILDINGS_LAYER_ID = 'urban-buildings-3d';
export const BUILDING_LAYER_IDS = [BUILDINGS_LAYER_ID, 'dataset-synthetic-buildings'];
export const BUILDING_PAINT: FillExtrusionLayerSpecification['paint'] = {
  'fill-extrusion-color': '#a9b6ae',
  // Some Goong areas use 0 for unavailable height. A zero extrusion coincides
  // with terrain; use the existing visual-only fallback, never a measured Z.
  'fill-extrusion-height': ['case',
    ['>', ['to-number', ['get', 'max_height'], 0], 0], ['to-number', ['get', 'max_height'], 12],
    ['>', ['to-number', ['get', 'height'], 0], 0], ['to-number', ['get', 'height'], 12],
    ['>', ['to-number', ['get', 'render_height'], 0], 0], ['to-number', ['get', 'render_height'], 12],
    ['>', ['to-number', ['get', 'building:height'], 0], 0], ['to-number', ['get', 'building:height'], 12],
    12,
  ],
  'fill-extrusion-base': ['to-number', ['coalesce', ['get', 'min_height'], ['get', 'render_min_height'], 0], 0],
};

function firstLabelLayer(style: StyleSpecification): string | undefined {
  return style.layers?.find(
    (layer) => layer.type === 'symbol' && Boolean(layer.layout?.['text-field']),
  )?.id;
}

export function setBuildings3d(map: MapLibreMap, enabled: boolean, opacity = 0.8): boolean {
  // The Goong style already extrudes VN_Building. Two overlapping versions
  // produce z-fighting and make the visible surface disagree with picking.
  const style = map.getStyle();
  for (const layer of style.layers ?? []) {
    if (layer.type === 'fill-extrusion' && layer.id !== BUILDINGS_LAYER_ID
      && layer.source === 'composite' && layer['source-layer'] === 'VN_Building') {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }
  if (!enabled) {
    if (map.getLayer(BUILDINGS_LAYER_ID)) map.removeLayer(BUILDINGS_LAYER_ID);
    return true;
  }

  if (map.getLayer(BUILDINGS_LAYER_ID)) {
    map.setPaintProperty(BUILDINGS_LAYER_ID, 'fill-extrusion-opacity', opacity);
    map.moveLayer(BUILDINGS_LAYER_ID, firstLabelLayer(map.getStyle()));
    return true;
  }
  const hasBuildingSourceLayer = style.layers?.some(
    (layer) => 'source-layer' in layer && layer['source-layer'] === 'VN_Building',
  );
  if (!style.sources?.composite || !hasBuildingSourceLayer) return false;

  map.addLayer(
    {
      id: BUILDINGS_LAYER_ID,
      source: 'composite',
      'source-layer': 'VN_Building',
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
