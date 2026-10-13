import type { Position } from 'geojson';
import type { PolygonGeometry } from './types';

const polygons = (g: PolygonGeometry) => g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
function inRing(p: Position, ring: Position[]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}
function inside(p: Position, rings: Position[][]) { return inRing(p, rings[0]) && !rings.slice(1).some(r => inRing(p, r)); }
function crosses(a: Position, b: Position, c: Position, d: Position) {
  const orient = (p: Position, q: Position, r: Position) => (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
  const on = (p: Position, q: Position, r: Position) => r[0] >= Math.min(p[0], q[0]) && r[0] <= Math.max(p[0], q[0]) && r[1] >= Math.min(p[1], q[1]) && r[1] <= Math.max(p[1], q[1]);
  const x = orient(a,b,c), y = orient(a,b,d), z = orient(c,d,a), w = orient(c,d,b);
  return (x*y < 0 && z*w < 0) || (x === 0 && on(a,b,c)) || (y === 0 && on(a,b,d)) || (z === 0 && on(c,d,a)) || (w === 0 && on(c,d,b));
}
/** Visual suppression only. Server-side projected geometry remains authoritative. */
export function polygonsIntersect(a: PolygonGeometry, b: PolygonGeometry): boolean {
  return polygons(a).some(pa => polygons(b).some(pb => {
    if (pa[0].some(p => inside(p, pb)) || pb[0].some(p => inside(p, pa))) return true;
    return pa.some(ra => pb.some(rb => ra.slice(1).some((p, i) => rb.slice(1).some((q, j) => crosses(ra[i], p, rb[j], q)))));
  }));
}
