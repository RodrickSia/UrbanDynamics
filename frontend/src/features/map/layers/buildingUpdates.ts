import type { Map as MapLibreMap } from 'maplibre-gl';

// Owners notify after changing building layers, before MapLibre evaluates paint
// for the next frame. styledata alone fires after that evaluation.
const observers = new WeakMap<MapLibreMap, () => void>();
export function watchBuildingUpdates(map: MapLibreMap, update: () => void) {
  observers.set(map, update);
  return () => { if (observers.get(map) === update) observers.delete(map); };
}
export function notifyBuildingUpdates(map: MapLibreMap) { observers.get(map)?.(); }
