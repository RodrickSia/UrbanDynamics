import type { MapMode, MeasurementPoint } from '../types/map';
import { createAreaFrame, cross, dot, normalize, subtract, type GeographicPosition, type Vector3 } from './measurementAreaFrame';

type Point2 = [number, number];
export interface AreaMeasurement {
  valid: boolean;
  reason: string;
  calculationMode: 'planar' | 'horizontal';
  elevationAvailable: boolean;
  areaSquareMeters: number;
  perimeterMeters: number;
  vertices: GeographicPosition[];
  coordinates: Point2[];
  triangles: number[];
  areaAnchor?: GeographicPosition;
  perimeterAnchor?: GeographicPosition;
}
const turn = (a: Point2, b: Point2, c: Point2) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const EPS = 1e-7;

/** Simple polygon only: crossings/touching nonadjacent edges are not measurable rings. */
function intersects(a: Point2, b: Point2, c: Point2, d: Point2): boolean {
  const on = (p: Point2, q: Point2, r: Point2) => Math.abs(turn(p,q,r)) < EPS
    && r[0] >= Math.min(p[0],q[0])-EPS && r[0] <= Math.max(p[0],q[0])+EPS
    && r[1] >= Math.min(p[1],q[1])-EPS && r[1] <= Math.max(p[1],q[1])+EPS;
  return (turn(a,b,c)*turn(a,b,d) < 0 && turn(c,d,a)*turn(c,d,b) < 0)
    || on(a,b,c) || on(a,b,d) || on(c,d,a) || on(c,d,b);
}

/** Ear clipping after ring validation; no holes, no new runtime dependency. */
function triangulate(points: Point2[], winding: number): number[] {
  const remaining = points.map((_,i) => i), triangles: number[] = [];
  while (remaining.length > 3) {
    let clipped = false;
    for (let i = 0; i < remaining.length; i++) {
      const a = remaining[(i+remaining.length-1)%remaining.length], b = remaining[i], c = remaining[(i+1)%remaining.length];
      const orientation = turn(points[a],points[b],points[c])*winding;
      if (Math.abs(orientation) < EPS) { remaining.splice(i,1); clipped = true; break; }
      if (orientation < 0) continue;
      const occupied = remaining.some(j => j !== a && j !== b && j !== c
        && turn(points[a],points[b],points[j])*winding >= -EPS
        && turn(points[b],points[c],points[j])*winding >= -EPS
        && turn(points[c],points[a],points[j])*winding >= -EPS);
      if (occupied) continue;
      triangles.push(a,b,c); remaining.splice(i,1); clipped = true; break;
    }
    if (!clipped) return [];
  }
  return [...triangles, ...remaining];
}

export function calculateAreaMeasurement(input: MeasurementPoint[], mode: MapMode): AreaMeasurement {
  const result: AreaMeasurement = { valid: false, reason: 'Select at least 3 points',
    calculationMode: 'horizontal', elevationAvailable: input.every(p => p.elevationAvailable),
    areaSquareMeters: 0, perimeterMeters: 0, vertices: [], coordinates: [], triangles: [] };
  if (input.length < 3) return result;
  const fail = (reason: string) => ({ ...result, reason });
  if (input.length > 256) return fail('Maximum 256 vertices');
  if (input.some(p => ![p.longitude,p.latitude,p.elevationMeters].every(Number.isFinite)
    || Math.abs(p.latitude) > 85 || Math.abs(p.longitude) > 180)) return fail('Invalid coordinates');
  const frame = createAreaFrame(input[0]);
  const local = input.map(p => frame.toLocal(p));
  const points = [...input];
  if (Math.hypot(...subtract(local[0],local.at(-1)!)) < 0.001) { local.pop(); points.pop(); }
  if (local.length < 3) return result;
  const extent = Math.max(...local.map(p => Math.hypot(...p)));
  if (extent > 100_000) return fail('Local measurement limit: 100 km');
  let normal: Vector3 = [0,0,0];
  for (let i = 1; i < local.length; i++) for (let j = i+1; j < local.length; j++) {
    const candidate = cross(local[i],local[j]);
    if (Math.hypot(...candidate) > Math.hypot(...normal)) normal = candidate;
  }
  if (Math.hypot(...normal) < 1e-4) return fail('Points must enclose an area');
  normal = normalize(normal);
  const planar = mode === '3d' && result.elevationAvailable
    && local.every(p => Math.abs(dot(p,normal)) <= 0.05 + extent*1e-6);
  result.calculationMode = planar ? 'planar' : 'horizontal';
  const u = normalize(local.find(p => Math.hypot(...p) > 0.001)!);
  const v = normalize(cross(normal,u));
  const height = Math.max(...points.map(p => p.elevationMeters));
  result.coordinates = local.map(p => planar ? [dot(p,u),dot(p,v)] : [p[0],p[1]]);
  result.vertices = points.map((p,i) => planar
    ? frame.toGeographic(local[i].map((value,j) => value - dot(local[i],normal)*normal[j]) as Vector3)
    : { longitude: p.longitude, latitude: p.latitude, elevationMeters: mode === '3d' ? height : 0 });
  const ring = result.coordinates, n = ring.length;
  let twiceArea = 0, perimeter = 0, longest = 0, longestIndex = 0;
  for (let i = 0; i < n; i++) {
    const a = ring[i], b = ring[(i+1)%n];
    const length = Math.hypot(b[0]-a[0], b[1]-a[1]);
    if (length < 0.001) return fail('Remove duplicate vertices');
    twiceArea += a[0]*b[1]-b[0]*a[1]; perimeter += length;
    if (length > longest) { longest = length; longestIndex = i; }
    for (let j = i+1; j < n; j++) {
      if (j === i+1 || (i === 0 && j === n-1)) continue;
      if (intersects(a,b,ring[j],ring[(j+1)%n])) return fail('Polygon edges must not cross');
    }
  }
  if (Math.abs(twiceArea) < 0.0002) return fail('Points must enclose an area');
  result.triangles = triangulate(ring, Math.sign(twiceArea));
  if (!result.triangles.length) return fail('Polygon could not be triangulated');
  const average = (indices: number[]): GeographicPosition => {
    const values = indices.map(i => frame.toLocal(result.vertices[i]));
    return frame.toGeographic([0,1,2].map(j => values.reduce((sum,p) => sum+p[j],0)/values.length) as Vector3);
  };
  // The largest triangle's centroid always lies inside a concave polygon.
  let bestTriangle = result.triangles.slice(0,3), bestArea = 0;
  for (let i = 0; i < result.triangles.length; i += 3) {
    const triangle = result.triangles.slice(i,i+3);
    const area = Math.abs(turn(ring[triangle[0]],ring[triangle[1]],ring[triangle[2]]));
    if (area > bestArea) { bestArea = area; bestTriangle = triangle; }
  }
  return { ...result, valid: true, reason: '', areaSquareMeters: Math.abs(twiceArea)/2,
    perimeterMeters: perimeter, areaAnchor: average(bestTriangle),
    perimeterAnchor: average([longestIndex,(longestIndex+1)%n]) };
}
