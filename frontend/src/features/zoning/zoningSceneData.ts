import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { rings, sketchGeometry } from './geometry';
import type { ZoningBridge } from './types';

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const DRAW_COLOR = '#FF6D00';
const AREA_COLOR = '#2877dc';
function feature(geometry: Geometry, properties: Record<string, unknown>): Feature { return { type: 'Feature', geometry, properties }; }

export function zoningData(bridge: ZoningBridge): FeatureCollection {
  if (!bridge.active) return EMPTY;
  const features: Feature[] = [];
  if (!bridge.plan) for (const [id, geometry] of Object.entries(bridge.displayedPlans ?? {})) {
    features.push(feature(geometry, { kind: 'plan-preview', id, color: AREA_COLOR, alpha: .07, width: 2.5 }));
  }
  if (!bridge.plan && bridge.visible) for (const { plan, scenario } of bridge.displayedPlanScenes ?? []) {
    for (const zone of scenario.zones) {
      const type = plan.types.find(item => item.id === zone.type_id);
      features.push(feature(zone.geometry, { kind: 'plan-zone-preview', id: zone.id, planId: plan.id,
        color: type?.color ?? '#6d8588', alpha: .26, width: 1.5 }));
    }
  }
  if (bridge.plan) features.push(feature(bridge.plan.study_area, { kind: 'study', color: AREA_COLOR, alpha: 0, width: 3 }));
  if (bridge.analysis?.active && bridge.analysis.geometry) features.push(feature(bridge.analysis.geometry,
    { kind: 'analysis', color: AREA_COLOR, alpha: .06, width: 3 }));
  if (bridge.visible) for (const zone of bridge.scenario?.zones ?? []) {
    const type = bridge.plan?.types.find(t => t.id === zone.type_id);
    features.push(feature(zone.geometry, { kind: 'zone', id: zone.id, label: type?.code ?? 'Unknown',
      color: type?.color ?? '#6d8588', alpha: bridge.sketch.tool ? 0 : bridge.opacity,
      width: bridge.selected.includes(zone.id) ? 4 : 1.5 }));
  }
  const draft = sketchGeometry(bridge.sketch);
  if (draft) features.push(feature(draft, { kind: 'draft', color: DRAW_COLOR, alpha: 0, width: 3 }));
  else if (bridge.sketch.points.length > 1) features.push(feature({ type: 'LineString', coordinates: bridge.sketch.points },
    { kind: 'draft', color: DRAW_COLOR, alpha: 0, width: 3 }));
  const editableRings = bridge.sketch.geometry && bridge.sketch.geometry.type !== 'LineString'
    ? rings(bridge.sketch.geometry).map(r => r.slice(0, -1)) : [bridge.sketch.points];
  editableRings.forEach((ring, r) => ring.forEach((point, i) => {
    features.push(feature({ type: 'Point', coordinates: point }, { kind: 'vertex', ring: r, index: i, color: DRAW_COLOR }));
    if (bridge.sketch.geometry && bridge.sketch.geometry.type !== 'LineString') {
      const next = ring[(i + 1) % ring.length];
      features.push(feature({ type: 'Point', coordinates: [(point[0] + next[0]) / 2, (point[1] + next[1]) / 2] },
        { kind: 'midpoint', ring: r, index: i, color: '#ffffff' }));
    }
  }));
  return { type: 'FeatureCollection', features };
}
