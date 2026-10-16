import type { Map as MapLibreMap, MapGeoJSONFeature } from 'maplibre-gl';

export type ScreenPoint = { x: number; y: number };

export interface LineSnap {
  feature: MapGeoJSONFeature;
  point: ScreenPoint;
  distance: number;
}

export function nearestDatasetLine(
  map: MapLibreMap,
  pointer: ScreenPoint,
  layers: string[],
  radius = 12,
): LineSnap | null {
  if (!layers.length || !map.isStyleLoaded()) return null;
  const bounds: [[number, number], [number, number]] = [
    [pointer.x - radius, pointer.y - radius],
    [pointer.x + radius, pointer.y + radius],
  ];
  let candidates: MapGeoJSONFeature[];
  try {
    candidates = map.queryRenderedFeatures(bounds, { layers });
  } catch {
    // A style swap can remove a queried layer between the visibility check and this call.
    return null;
  }
  let nearest: LineSnap | null = null;
  for (const feature of candidates) {
    const geometry = feature.geometry;
    const lines = geometry.type === 'LineString'
      ? [geometry.coordinates]
      : geometry.type === 'MultiLineString' ? geometry.coordinates : [];
    for (const line of lines) {
      for (let index = 1; index < line.length; index += 1) {
        const start = map.project({ lng: line[index - 1][0], lat: line[index - 1][1] });
        const end = map.project({ lng: line[index][0], lat: line[index][1] });
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const lengthSquared = dx * dx + dy * dy;
        const fraction = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1,
          ((pointer.x - start.x) * dx + (pointer.y - start.y) * dy) / lengthSquared,
        ));
        const point = { x: start.x + fraction * dx, y: start.y + fraction * dy };
        const distance = Math.hypot(pointer.x - point.x, pointer.y - point.y);
        if (distance <= radius && (!nearest || distance < nearest.distance)) {
          nearest = { feature, point, distance };
        }
      }
    }
  }
  return nearest;
}
