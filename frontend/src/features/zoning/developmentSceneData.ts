import type { Feature, FeatureCollection } from 'geojson';
import type { ZoningBridge } from './types';
import type { ProposedBuilding } from './developmentTypes';

function buildingFeatures(building: ProposedBuilding, selected: boolean, preview = false): Feature[] {
  // Coalesce matching adjacent floors so large uniform buildings remain one extrusion.
  const bands: { base: number; height: number; color: string; opacity: number }[] = [];
  for (const floor of building.floor_stack ?? []) {
    const opacity = floor.counts_gfa || floor.counts_far ? .85 : .4;
    const previous = bands.at(-1);
    if (previous && previous.color === floor.color && previous.opacity === opacity && previous.height === floor.base_m)
      previous.height = floor.top_m;
    else bands.push({ base: floor.base_m, height: floor.top_m, color: floor.color, opacity });
  }
  if (!bands.length) bands.push({ base: 0, height: building.height_m, color: building.color, opacity: .85 });
  return bands.map((band, index) => ({ type: 'Feature', id: `${building.id}:${index}`, geometry: building.geometry,
    properties: { kind: 'building', id: preview ? 'preview' : building.id, ...band,
      outline: selected || preview ? '#2877dc' : band.color } }));
}

export function developmentData(b: ZoningBridge): FeatureCollection {
  const features: Feature[] = [];
  if (!b.active) return { type: 'FeatureCollection', features };
  const preview = b.development?.preview;
  for (const building of b.scenario?.buildings ?? []) {
    if (preview?.id === building.id) continue;
    features.push(...buildingFeatures(building, building.id === b.development?.selectedBuilding));
  }
  if (preview) features.push(...buildingFeatures(preview, true, true));
  if (b.development?.active && b.development.parcel) features.push({ type: 'Feature', geometry: b.development.parcel.geometry,
    properties: { kind: 'parcel', color: '#2877dc' } });
  for (const mask of b.scenario?.demolition_masks ?? []) features.push({ type: 'Feature', geometry: mask.geometry,
    properties: { kind: 'demolition', color: '#bb7934' } });
  return { type: 'FeatureCollection', features };
}


