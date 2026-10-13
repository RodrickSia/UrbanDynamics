import type { Feature, FeatureCollection } from 'geojson';
import type { ZoningBridge } from './types';

export function developmentData(b: ZoningBridge): FeatureCollection {
  const features: Feature[] = [];
  if (!b.active) return { type: 'FeatureCollection', features };
  const preview = b.development?.preview;
  for (const building of b.scenario?.buildings ?? []) {
    if (preview?.id === building.id) continue;
    features.push({ type: 'Feature', id: building.id, geometry: building.geometry, properties: {
      kind: 'building', id: building.id, height: building.height_m,
      color: building.id === b.development?.selectedBuilding ? '#2877dc' : building.color,
    } });
  }
  if (preview) features.push({ type: 'Feature', geometry: preview.geometry, properties: {
    kind: 'building', id: 'preview', height: preview.height_m, color: '#2877dc',
  } });
  if (b.development?.active && b.development.parcel) features.push({ type: 'Feature', geometry: b.development.parcel.geometry,
    properties: { kind: 'parcel', color: '#2877dc' } });
  for (const mask of b.scenario?.demolition_masks ?? []) features.push({ type: 'Feature', geometry: mask.geometry,
    properties: { kind: 'demolition', color: '#bb7934' } });
  return { type: 'FeatureCollection', features };
}


