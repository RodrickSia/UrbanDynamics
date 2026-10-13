import { describe, expect, it } from 'vitest';
import type { Feature } from 'geojson';
import { planBuildings } from './planBuildingGeometry';
import type { PolygonGeometry } from './types';

const rect = (x: number, y: number, x2: number, y2: number): PolygonGeometry => ({ type: 'Polygon', coordinates: [
  [[x,y],[x2,y],[x2,y2],[x,y2],[x,y]],
] });
const feature = (geometry: PolygonGeometry, id?: number): Feature => ({ type: 'Feature', id, geometry, properties: { height: 20 } });
describe('plan building geometry', () => {
  it('clips crossing footprints and drops outside buildings without shifting their positions', () => {
    const result = planBuildings([feature(rect(1,1,3,3),1), feature(rect(8,2,12,5),2), feature(rect(12,12,15,15),3)], rect(0,0,10,10), []);
    expect(result.features.map(f => f.id)).toEqual([1,2]);
    expect(result.features[1].geometry).toEqual({ type: 'MultiPolygon', coordinates: [[[[8,2],[10,2],[10,5],[8,5],[8,2]]]] });
    expect(result.features[1].properties).toEqual({ height: 20 });
  });
  it('unions overlapping tile fragments, preserves holes and removes duplicates without IDs', () => {
    const duplicate = feature(rect(1,1,2,2));
    const result = planBuildings([duplicate, duplicate, feature(rect(3,3,7,6),7), feature(rect(5,3,8,6),7)],
      { type: 'Polygon', coordinates: [...(rect(0,0,10,10) as { coordinates: number[][][] }).coordinates,
        [[4,4],[4,5],[5,5],[5,4],[4,4]]] }, []);
    expect(result.features).toHaveLength(2);
    expect(result.features[1].geometry.type).toBe('MultiPolygon');
    expect((result.features[1].geometry as { coordinates: number[][][][] }).coordinates[0]).toHaveLength(2);
  });
  it('applies demolition even when a provider building has no ID', () => {
    expect(planBuildings([feature(rect(2,2,4,4))], rect(0,0,10,10), [rect(3,3,5,5)]).features).toEqual([]);
  });
  it('normalizes vector tile properties for the GeoJSON worker serializer', () => {
    const building = feature(rect(2,2,4,4), 1);
    building.properties = Object.assign(Object.create(null), { height: 20 });
    const result = planBuildings([building], rect(0,0,10,10), []);
    expect(Object.getPrototypeOf(result.features[0].properties)).toBe(Object.prototype);
    expect(result.features[0].properties).toEqual({ height: 20 });
  });
});
