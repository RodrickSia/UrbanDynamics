import { intersection, union, type MultiPolygon } from 'polygon-clipping';
import type { Feature, FeatureCollection } from 'geojson';
import type { PolygonGeometry } from './types';
import { polygonsIntersect } from './developmentGeometry';

/** Tile fragments may overlap. Union each provider ID before clipping once. */
export function planBuildings(features: Feature[], study: PolygonGeometry, masks: PolygonGeometry[]): FeatureCollection {
  const groups = new Map<string, { feature: Feature; parts: MultiPolygon[] }>();
  const seen = new Set<string>();
  for (const feature of features) {
    if (feature.geometry.type !== 'Polygon' && feature.geometry.type !== 'MultiPolygon') continue;
    const geometry = feature.geometry;
    const signature = JSON.stringify([feature.id, feature.properties, geometry]);
    if (seen.has(signature)) continue;
    seen.add(signature);
    if (!polygonsIntersect(geometry, study)) continue;
    const key = feature.id === undefined ? signature : String(feature.id);
    const group = groups.get(key) ?? { feature, parts: [] };
    group.parts.push((geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates) as MultiPolygon);
    groups.set(key, group);
  }
  const result: Feature[] = [];
  for (const { feature, parts } of groups.values()) {
    const geometry: PolygonGeometry = { type: 'MultiPolygon', coordinates: parts.length === 1 ? parts[0] : union(parts[0], ...parts.slice(1)) };
    if (masks.some(mask => polygonsIntersect(geometry, mask))) continue;
    const clipped = intersection(geometry.coordinates as MultiPolygon, study.coordinates as MultiPolygon);
    // Vector tile properties have a null prototype. MapLibre's worker serializer
    // requires plain objects when these features become a GeoJSON source.
    if (clipped.length) result.push({ type: 'Feature', id: feature.id, properties: { ...feature.properties },
      geometry: { type: 'MultiPolygon', coordinates: clipped } });
  }
  return { type: 'FeatureCollection', features: result };
}
