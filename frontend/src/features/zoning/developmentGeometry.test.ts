import { describe, expect, it } from 'vitest';
import type { PolygonGeometry, ZoningBridge } from './types';
import { polygonsIntersect } from './developmentGeometry';
import { developmentData } from './developmentSceneData';

const square = (x: number, y: number, size = 1): PolygonGeometry => ({ type: 'Polygon', coordinates: [[[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]]] });
describe('scenario geometry visibility', () => {
  it('masks crossing and contained footprints, but not buildings in holes or outside', () => {
    expect(polygonsIntersect(square(0,0), square(.8,.8))).toBe(true);
    expect(polygonsIntersect(square(0,0,5), square(1,1))).toBe(true);
    expect(polygonsIntersect(square(0,0), square(2,2))).toBe(false);
    const outer = square(0,0,5), hole = square(1,1,3);
    if (outer.type !== 'Polygon' || hole.type !== 'Polygon') throw Error('fixture');
    outer.coordinates.push(hole.coordinates[0]);
    expect(polygonsIntersect(outer, square(2,2,.5))).toBe(false);
  });
  it('uses only active scenario buildings and removes all features when closed', () => {
    const bridge = { active: true, scenario: { buildings: [{ id: 'a', geometry: square(0,0), height_m: 9, color: '#D79B8C' }],
      demolition_masks: [] }, development: { active: false } } as unknown as ZoningBridge;
    expect(developmentData(bridge).features.map(f => f.properties?.id)).toEqual(['a']);
    expect(developmentData({ ...bridge, scenario: { ...bridge.scenario!, buildings: [] } }).features).toEqual([]);
    expect(developmentData({ ...bridge, active: false }).features).toEqual([]);
  });
  it('stacks mixed floor colors at their actual heights and coalesces adjacent equal uses', () => {
    const bridge = { active: true, scenario: { buildings: [{ id: 'mixed', geometry: square(0,0), height_m: 10.9, color: '#D79B8C',
      floor_stack: [
        { base_m: 0, top_m: 4.5, color: '#C18EAD', counts_gfa: true, counts_far: true },
        { base_m: 4.5, top_m: 7.7, color: '#D79B8C', counts_gfa: true, counts_far: true },
        { base_m: 7.7, top_m: 10.9, color: '#D79B8C', counts_gfa: true, counts_far: true },
      ] }], demolition_masks: [] }, development: { selectedBuilding: 'mixed' } } as unknown as ZoningBridge;
    expect(developmentData(bridge).features.map(f => f.properties)).toEqual([
      { kind: 'building', id: 'mixed', base: 0, height: 4.5, color: '#C18EAD', opacity: .85, outline: '#2877dc' },
      { kind: 'building', id: 'mixed', base: 4.5, height: 10.9, color: '#D79B8C', opacity: .85, outline: '#2877dc' },
    ]);
  });
});
