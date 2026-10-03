import type { Map as MapLibreMap } from 'maplibre-gl';

const DEM_SOURCE_ID = 'urban-terrain-dem';
const HILLSHADE_SOURCE_ID = 'urban-terrain-shading-dem';
const HILLSHADE_LAYER_ID = 'urban-terrain-hillshade';
export const TERRAIN_TILEJSON_URL = 'https://tiles.mapterhorn.com/tilejson.json';

export function setTerrain(map: MapLibreMap, enabled: boolean): void {
  if (!enabled) {
    map.setTerrain(null);
    if (map.getLayer(HILLSHADE_LAYER_ID)) map.removeLayer(HILLSHADE_LAYER_ID);
    if (map.getSource(HILLSHADE_SOURCE_ID)) map.removeSource(HILLSHADE_SOURCE_ID);
    if (map.getSource(DEM_SOURCE_ID)) map.removeSource(DEM_SOURCE_ID);
    return;
  }

  for (const id of [DEM_SOURCE_ID, HILLSHADE_SOURCE_ID]) {
    if (map.getSource(id)) continue;
    map.addSource(id, {
      type: 'raster-dem',
      url: TERRAIN_TILEJSON_URL,
      encoding: 'terrarium',
      tileSize: 512,
      // Vietnam uses the global 30 m DEM. Higher zoom requests return 404;
      // overzoom the available DEM instead of losing terrain near buildings.
      maxzoom: 12,
    });
  }

  if (!map.getLayer(HILLSHADE_LAYER_ID)) {
    const labelLayerId = map
      .getStyle()
      .layers?.find((layer) => layer.type === 'symbol' && Boolean(layer.layout?.['text-field']))?.id;
    map.addLayer(
      {
        id: HILLSHADE_LAYER_ID,
        type: 'hillshade',
        source: HILLSHADE_SOURCE_ID,
        paint: {
          'hillshade-exaggeration': 0.42,
          'hillshade-shadow-color': '#244038',
          'hillshade-highlight-color': '#f6f4ea',
          'hillshade-accent-color': '#6f8078',
        },
      },
      labelLayerId,
    );
  }

  // Keep real-world elevation so buildings and measurement heights share one scale.
  map.setTerrain({ source: DEM_SOURCE_ID, exaggeration: 1 });
}
