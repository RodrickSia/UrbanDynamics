import type { Position } from 'geojson';
import type { PolygonGeometry, Sketch, SketchGeometry } from './types';

export function sketchGeometry(sketch: Sketch): SketchGeometry | null {
  if (sketch.geometry) return sketch.geometry;
  if (sketch.tool === 'split') return sketch.points.length >= 2 ? { type: 'LineString', coordinates: sketch.points } : null;
  return sketch.points.length >= 3 ? { type: 'Polygon', coordinates: [[...sketch.points, sketch.points[0]]] } : null;
}

export function rings(geometry: PolygonGeometry): Position[][] {
  return geometry.type === 'Polygon' ? geometry.coordinates : geometry.coordinates.flat();
}

export function editVertex(geometry: PolygonGeometry, ringIndex: number, index: number, point: Position | null, insert = false): PolygonGeometry {
  const copy = structuredClone(geometry);
  const ring = rings(copy)[ringIndex];
  ring.pop();
  if (insert && point) ring.splice(index + 1, 0, point);
  else if (point) ring[index] = point;
  else if (ring.length > 3) ring.splice(index, 1);
  ring.push([...ring[0]]);
  return copy;
}

export function areaText(value: number | null): string {
  if (value === null) return 'Unknown';
  return value >= 10000 ? `${(value / 10000).toLocaleString(undefined, { maximumFractionDigits: 2 })} ha`
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} m²`;
}
