import type { Map as MapLibreMap, MapGeoJSONFeature, PointLike } from 'maplibre-gl';
import type { MeasurementEdge, MeasurementSnap } from '../types/map';
import type { MeasurementProjection, MeasurementRay, Position3 } from './measurementProjection';
import { readTerrainElevation } from './terrainElevation';

interface WorldEdge { metadata: MeasurementEdge; a: Position3; b: Position3 }
export interface SnapGeometry {
  objectId: string;
  edges: WorldEdge[];
  vertices: { position: Position3; id: string; edges: MeasurementEdge[] }[];
}
export interface SnapCandidate {
  position: Position3;
  snap: MeasurementSnap;
  priority: number;
  distance: number;
}

export function buildingObjectId(feature: MapGeoJSONFeature): string {
  return `${feature.source ?? ''}:${feature.sourceLayer ?? ''}:${feature.properties?.gid ?? feature.properties?.feature_id ?? feature.id ?? JSON.stringify(feature.geometry)}`;
}

/** Build once per scene revision. Altitudes match the rendered extrusion plane. */
export function prepareSnapGeometry(
  map: MapLibreMap, feature: MapGeoJSONFeature, projection: MeasurementProjection, height: number,
): SnapGeometry {
  const geometry = feature.geometry;
  const polygons: number[][][][] = geometry.type === 'Polygon' ? [geometry.coordinates]
    : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  const objectId = buildingObjectId(feature);
  const edges = new Map<string, WorldEdge>();
  const vertices = new Map<string, SnapGeometry['vertices'][number]>();
  const geographic = (p: Position3): Position3 => {
    const m = new projection.Mercator(...p); const ll = m.toLngLat();
    return [ll.lng, ll.lat, m.toAltitude()];
  };
  const key = (p: Position3, level: 'base' | 'roof') => {
    const geo = geographic(p);
    // Identity describes topology, not DEM LOD or the current camera height.
    return `${geo[0].toFixed(8)},${geo[1].toFixed(8)}:${level}`;
  };
  const add = (a: Position3, b: Position3, levelA: 'base' | 'roof', levelB: 'base' | 'roof') => {
    const ak = key(a, levelA); const bk = key(b, levelB);
    if (ak === bk || Math.hypot(...a.map((v, i) => v - b[i])) < 1e-15) return;
    const id = `${objectId}:${[ak, bk].sort().join('/')}`;
    if (edges.has(id)) return;
    const metadata: MeasurementEdge = { id, objectId, start: geographic(a), end: geographic(b) };
    edges.set(id, { metadata, a, b });
    for (const [id, position] of [[ak, a], [bk, b]] as const) {
      let vertex = vertices.get(id);
      if (!vertex) { vertex = { id: `${objectId}:${id}`, position, edges: [] }; vertices.set(id, vertex); }
      vertex.edges.push(metadata);
    }
  };
  for (const polygon of polygons) {
    const points = polygon.flatMap(ring => ring.slice(0, -1))
      .map(p => projection.Mercator.fromLngLat([p[0], p[1]]));
    if (!points.length) continue;
    const center = new projection.Mercator(
      points.reduce((sum, p) => sum + p.x, 0) / points.length,
      points.reduce((sum, p) => sum + p.y, 0) / points.length,
    ).toLngLat();
    const ground = readTerrainElevation(map, center);
    // Unknown ground/building heights must not create apparently exact snaps.
    if (ground == null) continue;
    const minHeight = Number(feature.properties?.min_height ?? feature.properties?.render_min_height ?? 0);
    const base = projection.Mercator.fromLngLat(center, ground + (Number.isFinite(minHeight) ? Math.max(0, minHeight) : 0)).z;
    const roof = projection.Mercator.fromLngLat(center, ground + height).z;
    for (const ring of polygon) for (let i = 1; i < ring.length; i++) {
      const a = projection.Mercator.fromLngLat([ring[i - 1][0], ring[i - 1][1]]);
      const b = projection.Mercator.fromLngLat([ring[i][0], ring[i][1]]);
      add([a.x, a.y, roof], [b.x, b.y, roof], 'roof', 'roof');
      add([a.x, a.y, base], [b.x, b.y, base], 'base', 'base');
      add([a.x, a.y, base], [a.x, a.y, roof], 'base', 'roof');
    }
  }
  return { objectId, edges: [...edges.values()], vertices: [...vertices.values()] };
}

/** Pixel proximity is only the hit tolerance; all returned positions are world-space. */
export function snapCandidates(
  geometry: SnapGeometry, screen: PointLike, projection: MeasurementProjection, width: number, height: number,
): SnapCandidate[] {
  const [x, y] = Array.isArray(screen) ? screen : [screen.x, screen.y];
  const candidates: SnapCandidate[] = [];
  for (const vertex of geometry.vertices) {
    const p = projection.project(vertex.position, width, height);
    if (!p?.visible) continue;
    const distance = Math.hypot(x - p.x, y - p.y);
    if (distance <= 8) candidates.push({ distance, position: vertex.position, priority: 0,
      snap: { kind: 'vertex', objectId: geometry.objectId, primitiveId: vertex.id, edges: vertex.edges } });
  }
  for (const edge of geometry.edges) {
    const a = projection.project(edge.a, width, height); const b = projection.project(edge.b, width, height);
    if (!a || !b) continue;
    const dx = b.x - a.x; const dy = b.y - a.y;
    const length2 = dx * dx + dy * dy;
    if (length2 < 1) continue;
    const q = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / length2));
    const distance = Math.hypot(x - a.x - q * dx, y - a.y - q * dy);
    if (distance > 6) continue;
    const m = projection.matrix;
    if (!m) continue;
    const w = (p: Position3) => m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
    // Correct screen interpolation for perspective before using it in world space.
    const t = q * w(edge.a) / ((1 - q) * w(edge.b) + q * w(edge.a));
    const position = edge.a.map((v, i) => v + t * (edge.b[i] - v)) as Position3;
    if (!projection.project(position, width, height)?.visible) continue;
    candidates.push({ distance, position, priority: 1,
      snap: { kind: 'edge', objectId: geometry.objectId, primitiveId: edge.metadata.id, edges: [edge.metadata] } });
  }
  return candidates;
}

export function rayParameter(ray: MeasurementRay, position: Position3): number {
  const d = ray.far.map((value, i) => value - ray.near[i]);
  return d.reduce((sum, v, i) => sum + v * (position[i] - ray.near[i]), 0)
    / d.reduce((sum, v) => sum + v * v, 0);
}
