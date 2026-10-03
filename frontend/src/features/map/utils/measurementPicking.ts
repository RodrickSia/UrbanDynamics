import type { Map as MapLibreMap, MapGeoJSONFeature, PointLike } from 'maplibre-gl';

import type { MeasurementProjection, MeasurementRay, Position3 } from './measurementProjection';
import { readTerrainElevation } from './terrainElevation';

export interface BuildingHit {
  rayDistance: number;
  coordinate: [number, number];
  elevation: number;
  groundElevation: number | null;
  heightAboveGround: number;
}

/** Intersect the pointer ray with roof and facade planes of an extrusion. */
export function pickBuildingSurface(
  map: MapLibreMap,
  feature: MapGeoJSONFeature,
  screen: PointLike,
  projection: MeasurementProjection,
  height: number,
  cameraRay?: MeasurementRay | null,
): BuildingHit | null {
  const canvas = map.getCanvas();
  const ray = cameraRay ?? projection.ray(screen, canvas.clientWidth, canvas.clientHeight);
  if (!ray) return null;
  const geometry = feature.geometry;
  const polygons: number[][][][] = geometry.type === 'Polygon' ? [geometry.coordinates]
    : geometry.type === 'MultiPolygon' ? geometry.coordinates : [];
  const direction = ray.far.map((value, index) => value - ray.near[index]);
  let nearest: { t: number; point: Position3; ground: number | null } | null = null;

  for (const polygon of polygons) {
    const outer = polygon[0];
    if (!outer?.length) continue;
    // Match MapLibre's mean of ring vertices in Mercator space, excluding
    // the duplicated closing vertex (fill_extrusion_bucket centroid).
    const vertices = polygon.flatMap((ring) => ring.slice(0, -1))
      .map((p) => projection.Mercator.fromLngLat([p[0], p[1]]));
    const center = new projection.Mercator(
      vertices.reduce((sum, p) => sum + p.x, 0) / vertices.length,
      vertices.reduce((sum, p) => sum + p.y, 0) / vertices.length,
    ).toLngLat();
    const anchor: [number, number] = [center.lng, center.lat];
    const ground = readTerrainElevation(map, anchor);
    const base = ground ?? 0;
    const roofZ = projection.Mercator.fromLngLat(anchor, base + height).z;
    const minHeight = Number(feature.properties?.min_height ?? feature.properties?.render_min_height ?? 0);
    const baseZ = projection.Mercator.fromLngLat(anchor, base + (Number.isFinite(minHeight) ? Math.max(0, minHeight) : 0)).z;
    const rings = polygon.map((ring) => ring.map((p) => {
      const m = projection.Mercator.fromLngLat([p[0], p[1]]);
      return [m.x, m.y] as [number, number];
    }));
    const consider = (t: number) => {
      if (t < 0 || t > 1 || (nearest && t >= nearest.t)) return;
      const point = ray.near.map((value, index) => value + t * direction[index]) as Position3;
      nearest = { t, point, ground };
    };
    if (Math.abs(direction[2]) > 1e-15) {
      const t = (roofZ - ray.near[2]) / direction[2];
      const xy: [number, number] = [ray.near[0] + t * direction[0], ray.near[1] + t * direction[1]];
      if (insideRing(xy, rings[0]) && !rings.slice(1).some((ring) => insideRing(xy, ring))) consider(t);
    }
    // Check every facade, including courtyard walls; pick the nearest surface.
    for (const ring of rings) {
      for (let index = 1; index < ring.length; index += 1) {
        const a = ring[index - 1];
        const b = ring[index];
        const edge = [b[0] - a[0], b[1] - a[1]];
        const denominator = direction[0] * edge[1] - direction[1] * edge[0];
        if (Math.abs(denominator) < 1e-20) continue;
        const delta = [a[0] - ray.near[0], a[1] - ray.near[1]];
        const t = (delta[0] * edge[1] - delta[1] * edge[0]) / denominator;
        const u = (delta[0] * direction[1] - delta[1] * direction[0]) / denominator;
        const z = ray.near[2] + t * direction[2];
        if (u >= 0 && u <= 1 && z >= baseZ && z <= roofZ) consider(t);
      }
    }
  }
  if (!nearest) return null;
  const hit = nearest as { t: number; point: Position3; ground: number | null };
  const mercator = new projection.Mercator(...hit.point);
  const lngLat = mercator.toLngLat();
  const elevation = mercator.toAltitude();
  return { rayDistance: hit.t, coordinate: [lngLat.lng, lngLat.lat], elevation,
    groundElevation: hit.ground, heightAboveGround: elevation - (hit.ground ?? 0) };
}

function insideRing(point: [number, number], ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const a = ring[i];
    const b = ring[j];
    if ((a[1] > point[1]) !== (b[1] > point[1])
      && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}
