import earcut from 'earcut';
import type { Map as MapLibreMap, MapGeoJSONFeature } from 'maplibre-gl';
import { BUILDINGS_LAYER_ID } from '../layers/buildings3d';
import { readBuildingHeight } from '../utils/measurementElevation';
import { readTerrainElevation } from '../utils/terrainElevation';
import { direction, frame, type GeoPoint, type Vec3, type Viewshed } from './math';

export interface SceneMesh {
  vertices: Float32Array;
  complete: boolean;
  message: string;
  step: number;
}
export interface SceneInput {
  elevation: (point: GeoPoint) => number | null;
  buildings: Pick<MapGeoJSONFeature, 'geometry' | 'properties'>[];
  buildingsAvailable: boolean;
}
const GRID = 48,
  MAX_VERTICES = 240_000;

/** Bounded, observer-relative mesh. Holes are triangulated, not filled in. */
export function buildScene(view: Viewshed, input: SceneInput): SceneMesh {
  const local = frame(view.observer);
  // Include the corners of the far plane, not just its center line.
  const range =
    direction(view).distance *
    Math.sqrt(
      1 +
        Math.tan((view.horizontalFov * Math.PI) / 360) ** 2 +
        Math.tan((view.verticalFov * Math.PI) / 360) ** 2,
    );
  const step = (2 * range) / GRID,
    vertices: number[] = [],
    samples: (Vec3 | null)[] = [];
  let complete = input.buildingsAvailable,
    unknown = 0;
  const triangle = (a: Vec3, b: Vec3, c: Vec3) => {
    if (vertices.length + 9 > MAX_VERTICES * 3) {
      complete = false;
      return;
    }
    vertices.push(...a, ...b, ...c);
  };
  for (let y = 0; y <= GRID; y++)
    for (let x = 0; x <= GRID; x++) {
      const p: Vec3 = [x * step - range, y * step - range, 0],
        geo = local.toGeo(p),
        z = input.elevation(geo);
      samples.push(z == null ? null : [p[0], p[1], z - view.observer.elevationMeters]);
      if (z == null) {
        complete = false;
        unknown++;
      }
    }
  for (let y = 0; y < GRID; y++)
    for (let x = 0; x < GRID; x++) {
      const i = y * (GRID + 1) + x,
        a = samples[i],
        b = samples[i + 1],
        c = samples[i + GRID + 1],
        d = samples[i + GRID + 2];
      if (a && b && c) triangle(a, b, c);
      if (b && c && d) triangle(b, d, c);
    }
  const seen = new Set<string>();
  for (const feature of input.buildings) {
    // Source queries include diagnostic footprints hidden by the render filter.
    // They must not create invisible occluders or imply complete scene coverage.
    if (feature.properties?.geometry_status === 'outside_parcels') {
      complete = false;
      continue;
    }
    if (vertices.length / 3 >= MAX_VERTICES) {
      complete = false;
      break;
    }
    const polygons: number[][][][] =
      feature.geometry.type === 'Polygon'
        ? [feature.geometry.coordinates]
        : feature.geometry.type === 'MultiPolygon'
          ? feature.geometry.coordinates
          : [];
    for (const polygon of polygons) {
      const rings = polygon.map((r) =>
        r
          .slice(0, -1)
          .map((p) => local.toLocal({ longitude: p[0], latitude: p[1], elevationMeters: 0 })),
      );
      const points = rings.flat();
      if (
        points.length < 3 ||
        points.length > 4096 ||
        points.some((p) => p.some((v) => !Number.isFinite(v)))
      ) {
        complete = false;
        continue;
      }
      if (
        Math.min(...points.map((p) => p[0])) > range ||
        Math.max(...points.map((p) => p[0])) < -range ||
        Math.min(...points.map((p) => p[1])) > range ||
        Math.max(...points.map((p) => p[1])) < -range
      )
        continue;
      const key = JSON.stringify(polygon);
      if (seen.has(key)) continue;
      seen.add(key);
      const height = readBuildingHeight(feature.properties);
      const center = local.toGeo([
        points.reduce((s, p) => s + p[0], 0) / points.length,
        points.reduce((s, p) => s + p[1], 0) / points.length,
        0,
      ]);
      const ground = input.elevation(center);
      if (height == null || ground == null) {
        complete = false;
        unknown++;
        continue;
      }
      const min = Number(
        feature.properties?.min_height ?? feature.properties?.render_min_height ?? 0,
      );
      const bottom =
        ground - view.observer.elevationMeters + (Number.isFinite(min) ? Math.max(0, min) : 0);
      const top = ground - view.observer.elevationMeters + height;
      const holes: number[] = [];
      let count = 0;
      rings.forEach((r, i) => {
        if (i) holes.push(count);
        count += r.length;
      });
      const indices = earcut(
        points.flatMap((p) => [p[0], p[1]]),
        holes,
      );
      for (let i = 0; i < indices.length; i += 3) {
        const [a, b, c] = indices
          .slice(i, i + 3)
          .map((index) => [points[index][0], points[index][1], top] as Vec3);
        triangle(a, b, c);
      }
      for (const ring of rings)
        for (let i = 0; i < ring.length; i++) {
          const a = ring[i],
            b = ring[(i + 1) % ring.length];
          triangle([a[0], a[1], bottom], [b[0], b[1], bottom], [b[0], b[1], top]);
          triangle([a[0], a[1], bottom], [b[0], b[1], top], [a[0], a[1], top]);
        }
    }
  }
  return {
    vertices: new Float32Array(vertices),
    complete,
    step,
    message: complete
      ? `Loaded scene · approximate · ${step.toFixed(1)} m terrain grid`
      : `Incomplete scene · ${unknown ? 'elevation missing' : 'building coverage unavailable'} · visible classification withheld`,
  };
}

export function readScene(map: MapLibreMap, view: Viewshed): SceneMesh {
  const layer = map.getStyle().layers.find((l) => l.id === BUILDINGS_LAYER_ID);
  const source = layer && 'source' in layer ? layer.source : null;
  const sourceLayer = layer && 'source-layer' in layer ? layer['source-layer'] : undefined;
  const active =
    !!layer &&
    layer.layout?.visibility !== 'none' &&
    map.getZoom() >= (layer.minzoom ?? 0) &&
    map.getZoom() < (layer.maxzoom ?? 24) &&
    map.getPaintProperty(layer.id, 'fill-extrusion-opacity') !== 0;
  // Source features include loaded offscreen geometry, unlike rendered-feature queries.
  // https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#querysourcefeatures
  const buildings =
    active && source ? map.querySourceFeatures(source, sourceLayer ? { sourceLayer } : {}) : [];
  const mesh = buildScene(view, {
    buildings,
    buildingsAvailable: !active || (!!source && map.isSourceLoaded(source)),
    elevation: (p) => readTerrainElevation(map, [p.longitude, p.latitude]),
  });
  if (!active && mesh.complete)
    mesh.message = `Terrain only · approximate · ${mesh.step.toFixed(1)} m grid`;
  return mesh;
}
