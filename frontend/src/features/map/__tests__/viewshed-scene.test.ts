import { describe, expect, it } from 'vitest';
import { buildScene } from '../viewshed/scene';
import { createViewshed, frame } from '../viewshed/math';

describe('viewshed occlusion geometry', () => {
  const view = createViewshed('v', { longitude: 106, latitude: 10, elevationMeters: 2 });
  const f = frame(view.observer);
  const ring = (size: number) =>
    [
      [-size, -size],
      [size, -size],
      [size, size],
      [-size, size],
      [-size, -size],
    ].map(([x, y]) => {
      const p = f.toGeo([x, y, 0]);
      return [p.longitude, p.latitude];
    });
  it('creates terrain and real roof/facade geometry but never substitutes unknown building heights', () => {
    const ground = buildScene(view, {
      elevation: () => 0,
      buildings: [],
      buildingsAvailable: true,
    });
    const geometry = { type: 'Polygon' as const, coordinates: [ring(10), ring(3)] };
    const building = buildScene(view, {
      elevation: () => 0,
      buildings: [{ geometry, properties: { height: 20 } }],
      buildingsAvailable: true,
    });
    expect(building.vertices.length).toBeGreaterThan(ground.vertices.length);
    expect(building.complete).toBe(true);
    let roofArea=0;
    for(let i=0;i<building.vertices.length;i+=9){
      const v=building.vertices.slice(i,i+9);
      if(v[2]===18&&v[5]===18&&v[8]===18)roofArea+=Math.abs((v[3]-v[0])*(v[7]-v[1])-(v[6]-v[0])*(v[4]-v[1]))/2;
    }
    expect(roofArea).toBeCloseTo(20*20-6*6,2);
    const unknown = buildScene(view, {
      elevation: () => 0,
      buildings: [{ geometry, properties: { height: 0 } }],
      buildingsAvailable: true,
    });
    expect(unknown.vertices.length).toBe(ground.vertices.length);
    expect(unknown.complete).toBe(false);
    const excluded = buildScene(view, {
      elevation: () => 0,
      buildings: [{ geometry, properties: { height_m: 46, geometry_status: 'outside_parcels' } }],
      buildingsAvailable: true,
    });
    expect(excluded.vertices).toEqual(ground.vertices);
    expect(excluded.complete).toBe(false);
  });
  it('does not turn missing DEM into flat ground or visible results', () => {
    const mesh = buildScene(view, {
      elevation: () => null,
      buildings: [],
      buildingsAvailable: true,
    });
    expect(mesh.vertices.length).toBe(0);
    expect(mesh.complete).toBe(false);
  });
});
