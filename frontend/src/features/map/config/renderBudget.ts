import type { Map as MapLibreMap } from 'maplibre-gl';

// Cap unused tiles per source. Active visible tiles are managed separately by LOD.
export const MAP_CACHE_BUDGET = { maxTileCacheZoomLevels: 2, maxTileCacheSize: 64 } as const;

export function configureSceneLod(map: MapLibreMap): void {
  if (map.getSource('composite')) {
    // Keep nearby source detail and avoid over-downsampling buildings at the horizon.
    // A bounded tile-count ratio prevents requesting uniformly detailed distant tiles.
    map.setSourceTileLodParams(4, 3, 'composite');
  }
}
