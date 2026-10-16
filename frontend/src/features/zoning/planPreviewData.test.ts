import { describe, expect, it } from 'vitest';
import { developmentData } from './developmentSceneData';
import { zoningData } from './zoningSceneData';
import type { Plan, ZoningBridge } from './types';

const study = { type: 'Polygon' as const, coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] };
const plan = { id: 'plan-1', study_area: study,
  types: [{ id: 'res', code: 'RES', color: '#ff6d00' }],
  scenarios: [{ id: 'existing', kind: 'reference', zones: [], buildings: [] },
    { id: 'proposal', kind: 'proposal', zones: [{ id: 'zone-1', type_id: 'res', geometry: study }],
      buildings: [{ id: 'building-1', geometry: { type: 'Polygon', coordinates: [[[1, 1], [3, 1], [3, 2], [1, 2], [1, 1]]] },
        color: '#ff6d00', height_m: 12, floor_stack: [] }] }] } as unknown as Plan;
const bridge = (shown: boolean): ZoningBridge => ({ active: true, plan: null, scenario: null,
  displayedPlans: shown ? { [plan.id]: study } : {},
  displayedPlanScenes: shown ? [{ plan, scenario: plan.scenarios[1] }] : [],
  visible: true, selected: [], sketch: { tool: null, points: [], geometry: null }, opacity: .35,
} as unknown as ZoningBridge);

describe('plan list map preview', () => {
  it('shows the saved zoning type and clips proposed buildings to the study area', () => {
    const zoning = zoningData(bridge(true)).features;
    expect(zoning.find(item => item.properties?.kind === 'plan-zone-preview')?.properties?.color).toBe('#ff6d00');
    const buildings = developmentData(bridge(true)).features;
    expect(buildings).toHaveLength(1);
    expect(buildings[0].properties?.kind).toBe('building');
    expect(JSON.stringify(buildings[0].geometry)).not.toContain('[3,1]');
  });

  it('removes plan contents when its visibility is turned off', () => {
    expect(zoningData(bridge(false)).features).toHaveLength(0);
    expect(developmentData(bridge(false)).features).toHaveLength(0);
  });
});
