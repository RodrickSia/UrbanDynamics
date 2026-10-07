import { describe, expect, it } from 'vitest';
import type { MeasurementPoint } from '../types/map';
import { calculateAreaMeasurement } from '../utils/measurementArea';
import { createAreaFrame } from '../utils/measurementAreaFrame';
import { formatArea, formatLength } from '../utils/measurementUnits';

const frame = createAreaFrame({ longitude: 106.7, latitude: 10.8, elevationMeters: 80 });
const points = (coordinates: number[][]): MeasurementPoint[] => coordinates.map(([x,y,z = 0], i) => ({
  ...frame.toGeographic([x,y,z]), id: String(i), elevationAvailable: true, surface: 'building',
}));

describe('world-space polygon measurements', () => {
  it('measures a 3D inclined plane and its closed perimeter', () => {
    const result = calculateAreaMeasurement(points([[0,0,0],[4,0,3],[4,10,3],[0,10,0]]), '3d');
    expect(result.valid).toBe(true);
    expect(result.calculationMode).toBe('planar');
    expect(result.areaSquareMeters).toBeCloseTo(50, 4);
    expect(result.perimeterMeters).toBeCloseTo(30, 4);
    expect(result.triangles).toHaveLength(6);
  });
  it('handles a vertical facade without projecting its area to zero', () => {
    const result = calculateAreaMeasurement(points([[0,0,0],[10,0,0],[10,0,20],[0,0,20]]), '3d');
    expect(result.valid).toBe(true);
    expect(result.areaSquareMeters).toBeCloseTo(200, 4);
    expect(result.perimeterMeters).toBeCloseTo(60, 4);
  });
  it('uses horizontal projection for BOTH values when not coplanar', () => {
    const vertices = points([[0,0,0],[10,0,0],[10,10,8],[0,10,0]]);
    const result = calculateAreaMeasurement(vertices, '3d');
    expect(result.calculationMode).toBe('horizontal');
    expect(result.areaSquareMeters).toBeCloseTo(100, 3);
    expect(result.perimeterMeters).toBeCloseTo(40, 3);
    expect(calculateAreaMeasurement(vertices, '2d').areaSquareMeters).toBeCloseTo(100, 3);
  });
  it('triangulates concave polygons and is independent of winding', () => {
    const vertices = points([[0,0],[10,0],[10,10],[5,5],[0,10]]);
    for (const ring of [vertices, [...vertices].reverse()]) {
      const result = calculateAreaMeasurement(ring, '3d');
      expect(result.valid).toBe(true);
      expect(result.areaSquareMeters).toBeCloseTo(75, 3);
      // Collinear vertices after an ear is removed need no zero-area triangle.
      let covered = 0;
      for (let i = 0; i < result.triangles.length; i += 3) {
        const [a,b,c] = result.triangles.slice(i,i+3).map(j => result.coordinates[j]);
        covered += Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;
      }
      expect(covered).toBeCloseTo(75, 3);
    }
  });
  it('rejects crossings, duplicate edges and collinear points instead of showing fake areas', () => {
    expect(calculateAreaMeasurement(points([[0,0],[10,10],[0,10],[10,0]]), '3d').valid).toBe(false);
    expect(calculateAreaMeasurement(points([[0,0],[10,0],[10,0],[0,10]]), '3d').valid).toBe(false);
    expect(calculateAreaMeasurement(points([[0,0],[5,0],[10,0]]), '3d').valid).toBe(false);
  });
  it('normalizes a closing vertex and rejects invalid/oversized input', () => {
    expect(calculateAreaMeasurement(points([[0,0],[10,0],[0,10],[0,0]]), '3d').areaSquareMeters).toBeCloseTo(50, 3);
    expect(calculateAreaMeasurement(points([[0,0],[NaN,0],[0,10]]), '3d').valid).toBe(false);
    expect(calculateAreaMeasurement(points([[0,0],[150000,0],[0,10]]), '3d').reason).toContain('100 km');
  });
  it('triangulated area agrees with the boundary on concave and collinear rings', () => {
    // Deterministic radial polygons are simple, alternate concave/convex corners,
    // and exercise many ear orders without introducing a random flaky test.
    for (const n of [6,11,32,64]) {
      const polygon = points(Array.from({length:n},(_,i) => {
        const angle = 2*Math.PI*i/n, radius = i%2 ? 9 : 20;
        return [Math.cos(angle)*radius,Math.sin(angle)*radius,0];
      }));
      const result = calculateAreaMeasurement(polygon,'3d');
      expect(result.valid).toBe(true);
      let area = 0;
      for (let i=0;i<result.triangles.length;i+=3) {
        const [a,b,c] = result.triangles.slice(i,i+3).map(j=>result.coordinates[j]);
        area += Math.abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2;
      }
      expect(area).toBeCloseTo(result.areaSquareMeters,5);
    }
    expect(calculateAreaMeasurement(points([[0,0],[5,0],[10,0],[10,10],[0,10]]),'3d').areaSquareMeters).toBeCloseTo(100,3);
  });
  it('reports horizontal area with a warning when any elevation is unavailable', () => {
    const vertices = points([[0,0],[10,0],[10,10],[0,10]]);
    vertices[1].elevationAvailable = false;
    const result = calculateAreaMeasurement(vertices, '3d');
    expect(result.valid).toBe(true);
    expect(result.elevationAvailable).toBe(false);
    expect(result.calculationMode).toBe('horizontal');
    expect(result.areaSquareMeters).toBeCloseTo(100, 2);
  });
});

describe('coherent measurement units', () => {
  it('autoscales metric areas and lengths with consistent separators', () => {
    expect(formatArea(456.8, 'metric')).toBe('456.8 m²');
    expect(formatArea(12400, 'metric')).toBe('1.24 ha');
    expect(formatArea(1250000, 'metric')).toBe('1.25 km²');
    expect(formatLength(1234, 'metric')).toBe('1.23 km');
  });
  it('supports square feet and acres without mixing the perimeter units', () => {
    expect(formatArea(100, 'imperial')).toBe('1,076.39 ft²');
    expect(formatArea(4046.8564224, 'imperial')).toBe('1 acre');
    expect(formatLength(100, 'imperial')).toBe('328.08 ft');
  });
});
