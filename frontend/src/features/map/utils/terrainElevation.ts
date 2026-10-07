import type { LngLatLike, Map as MapLibreMap } from 'maplibre-gl';

export function readTerrainElevation(map: MapLibreMap, coordinate: LngLatLike): number | null {
  const terrain = map.getTerrain?.();
  // MapLibre returns zero for an unloaded DEM as well as for sea level.
  // Do not report that loading placeholder as an acquired height.
  const elevation = map.queryTerrainElevation(coordinate);
  // A nonzero local sample proves DEM coverage even while other tiles load.
  // Only zero is ambiguous with MapLibre's unloaded-tile placeholder.
  if (elevation === 0 && terrain && !map.isSourceLoaded(terrain.source)) return null;
  return elevation != null && Number.isFinite(elevation) ? elevation : null;
}
