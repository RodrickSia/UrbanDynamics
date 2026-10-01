import type { Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';

export const BUILDINGS_LAYER_ID = 'urban-buildings-3d';

function firstLabelLayer(style: StyleSpecification): string | undefined {
  return style.layers?.find(
    (layer) => layer.type === 'symbol' && Boolean(layer.layout?.['text-field']),
  )?.id;
}

export function setBuildings3d(map: MapLibreMap, enabled: boolean, opacity = 0.8): boolean {
  if (!enabled) {
    if (map.getLayer(BUILDINGS_LAYER_ID)) map.removeLayer(BUILDINGS_LAYER_ID);
    return true;
  }

  if (map.getLayer(BUILDINGS_LAYER_ID)) {
    map.setPaintProperty(BUILDINGS_LAYER_ID, 'fill-extrusion-opacity', opacity);
    return true;
  }
  const style = map.getStyle();
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
        'fill-extrusion-color': '#a9b6ae',
        'fill-extrusion-height': ['coalesce', ['to-number', ['get', 'height']], 12],
        'fill-extrusion-base': ['coalesce', ['to-number', ['get', 'min_height']], 0],
        'fill-extrusion-opacity': opacity,
      },
    },
    firstLabelLayer(style),
  );
  return true;
}
