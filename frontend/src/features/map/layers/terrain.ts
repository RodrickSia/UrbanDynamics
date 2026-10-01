import type { Map as MapLibreMap } from 'maplibre-gl';

const DEM_SOURCE_ID = 'goong-dem';
const HILLSHADE_LAYER_ID = 'goong-hillshade';

export function setTerrain(map: MapLibreMap, mapKey: string, enabled: boolean): void {
  if (!enabled) {
    map.setTerrain(null);
    if (map.getLayer(HILLSHADE_LAYER_ID)) map.removeLayer(HILLSHADE_LAYER_ID);
    if (map.getSource(DEM_SOURCE_ID)) map.removeSource(DEM_SOURCE_ID);
    return;
  }

  if (!map.getSource(DEM_SOURCE_ID)) {
    map.addSource(DEM_SOURCE_ID, {
      type: 'raster-dem',
      tiles: [`https://dem.goong.io/{z}/{x}/{y}.png?api_key=${encodeURIComponent(mapKey)}`],
      tileSize: 256,
      maxzoom: 15,
      encoding: 'terrarium',
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
        source: DEM_SOURCE_ID,
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

  map.setTerrain({ source: DEM_SOURCE_ID, exaggeration: 1.18 });
}
