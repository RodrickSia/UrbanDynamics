import type { LngLatLike, Map as MapLibreMap, MapGeoJSONFeature, PointLike } from 'maplibre-gl';

import { BUILDINGS_LAYER_ID } from '../layers/buildings3d';
import type { MapMode, MeasurementPoint } from '../types/map';
import type { MeasurementProjection } from './measurementProjection';
import { invalidateBuildingSurfaces, pickBuildingSurface } from './measurementPicking';
import { readTerrainElevation } from './terrainElevation';
import { buildingObjectId, prepareSnapGeometry, rayParameter, snapCandidates, type SnapGeometry } from './measurementSnap';
import type { MeasurementRay, Position3 } from './measurementProjection';

const BUILDING_HEIGHT_KEYS = ['height_m', 'max_height', 'height', 'render_height', 'building:height'] as const;
const buildingCandidates = new WeakMap<MapLibreMap, MapGeoJSONFeature[]>();
const snapGeometry = new WeakMap<MapLibreMap, Map<MapGeoJSONFeature, SnapGeometry>>();
let pointSequence = 0;

export function invalidateMeasurementPicking(map: MapLibreMap): void {
  buildingCandidates.delete(map);
  snapGeometry.delete(map);
  invalidateBuildingSurfaces(map);
}

export function readBuildingHeight(properties: Record<string, unknown> | null | undefined): number | null {
  if (!properties) return null;
  for (const key of BUILDING_HEIGHT_KEYS) {
    if (properties[key] == null || properties[key] === '') continue;
    const value = Number(properties[key]);
    if (!Number.isFinite(value) || value <= 0) continue;
    return value;
  }
  return null;
}

export function resolveMeasurementPoint(
  map: MapLibreMap,
  longitude: number,
  latitude: number,
  mode: MapMode,
  screenPoint?: PointLike,
  id?: string,
  projection?: MeasurementProjection,
): MeasurementPoint | null {
  const clickedCoordinate: [number, number] = [longitude, latitude];
  const queryPoint = screenPoint ?? map.project(clickedCoordinate);
  let building: MapGeoJSONFeature | undefined;
  let surfaceHit: ReturnType<typeof pickBuildingSurface> = null;
  if (mode === '3d' && map.getLayer(BUILDINGS_LAYER_ID)) {
    if (projection && screenPoint) {
      // MapLibre's extrusion point query projects heights without the terrain
      // offset. Gather visible candidates, then perform the real 3D ray test.
      let candidates = buildingCandidates.get(map);
      if (!candidates) {
        candidates = map.queryRenderedFeatures({ layers: [BUILDINGS_LAYER_ID] });
        buildingCandidates.set(map, candidates);
      }
      const canvas = map.getCanvas();
      const ray = projection.ray(screenPoint, canvas.clientWidth, canvas.clientHeight);
      for (const candidate of candidates) {
        const hit = pickBuildingSurface(map, candidate, screenPoint, projection,
          readBuildingHeight(candidate.properties) ?? 12, ray);
        if (hit && (!surfaceHit || hit.rayDistance < surfaceHit.rayDistance)) {
          surfaceHit = hit;
          building = candidate;
        }
      }
      if (ray && surfaceHit && terrainBlocks(map, projection, ray, screenPoint, surfaceHit.rayDistance)) {
        surfaceHit = null;
        building = undefined;
      }
      let geometryCache = snapGeometry.get(map);
      if (!geometryCache) { geometryCache = new Map(); snapGeometry.set(map, geometryCache); }
      const snaps = candidates.flatMap(candidate => {
        const height = readBuildingHeight(candidate.properties);
        if (height == null) return [];
        let geometry = geometryCache.get(candidate);
        if (!geometry) {
          geometry = prepareSnapGeometry(map, candidate, projection, height);
          if (geometry.vertices.length) geometryCache.set(candidate, geometry);
        }
        return snapCandidates(geometry, screenPoint, projection, canvas.clientWidth, canvas.clientHeight);
      }).sort((a, b) => a.priority - b.priority || a.distance - b.distance);
      for (const snap of snaps) {
        const pixel = projection.project(snap.position, canvas.clientWidth, canvas.clientHeight);
        if (!pixel) continue;
        const screen: [number, number] = [pixel.x, pixel.y];
        const snapRay = projection.ray(screen, canvas.clientWidth, canvas.clientHeight);
        if (!snapRay) continue;
        const t = rayParameter(snapRay, snap.position);
        const tolerance = rayTolerance(projection, snapRay, snap.position);
        if (terrainBlocks(map, projection, snapRay, screen, t, tolerance)) continue;
        // Reject occluded edges/vertices, including the far side of the same building.
        if (candidates.some(candidate => {
          const hit = pickBuildingSurface(map, candidate, screen, projection,
            readBuildingHeight(candidate.properties) ?? 12, snapRay);
          return hit && hit.rayDistance < t - tolerance;
        })) continue;
        const m = new projection.Mercator(...snap.position); const ll = m.toLngLat();
        const ground = readTerrainElevation(map, ll);
        return { id: id ?? nextPointId(), longitude: ll.lng, latitude: ll.lat,
          elevationMeters: m.toAltitude(), elevationAvailable: true, surface: 'building',
          buildingHeightMeters: m.toAltitude() - (ground ?? 0), snap: snap.snap };
      }
    } else {
      building = queryBuilding(map, queryPoint);
    }
  }
  const buildingHeight = readBuildingHeight(building?.properties);
  const anchoredCoordinate = surfaceHit?.coordinate ?? clickedCoordinate;
  const lngLat: LngLatLike = anchoredCoordinate;
  const terrainElevation = mode === '3d' ? readTerrainElevation(map, lngLat) : null;
  const groundElevation = terrainElevation ?? 0;
  if (!building && mode === '3d' && screenPoint && projection?.matrix) {
    const m = projection.Mercator.fromLngLat(anchoredCoordinate, groundElevation);
    const canvas = map.getCanvas();
    const projected = projection.project([m.x, m.y, m.z], canvas.clientWidth, canvas.clientHeight);
    const [x, y] = Array.isArray(screenPoint) ? screenPoint : [screenPoint.x, screenPoint.y];
    // unproject can fall back to the sea-level plane above the horizon. Do not
    // commit a behind-camera or distant fabricated hit when the pointer is sky.
    if (!projected?.visible || Math.hypot(projected.x - x, projected.y - y) > 8) return null;
  }
  if (building && buildingHeight != null && surfaceHit?.groundElevation != null) {
    return {
      id: id ?? nextPointId(),
      longitude: anchoredCoordinate[0],
      latitude: anchoredCoordinate[1],
      elevationMeters: surfaceHit.elevation,
      elevationAvailable: true,
      surface: 'building',
      buildingHeightMeters: surfaceHit.heightAboveGround,
      snap: { kind: 'face', objectId: buildingObjectId(building), primitiveId: surfaceHit.faceId },
    };
  }

  return {
    id: id ?? nextPointId(),
    longitude: anchoredCoordinate[0],
    latitude: anchoredCoordinate[1],
    elevationMeters: groundElevation,
    elevationAvailable: terrainElevation != null && !building,
    surface: building ? 'building' : terrainElevation != null ? 'terrain' : 'ground',
    snap: { kind: 'ground' },
    ...(surfaceHit && buildingHeight != null ? { buildingHeightMeters: surfaceHit.heightAboveGround } : {}),
  };
}

function rayTolerance(projection: MeasurementProjection, ray: MeasurementRay, position: Position3): number {
  const units = new projection.Mercator(...position).meterInMercatorCoordinateUnits();
  return 0.15 * units / Math.hypot(...ray.far.map((v, i) => v - ray.near[i]));
}

/** MapLibre 6's public unproject performs the terrain mesh raycast. Compare
 * its world-space depth with building hits rather than assuming buildings win. */
function terrainBlocks(map: MapLibreMap, projection: MeasurementProjection, ray: MeasurementRay,
  pixel: PointLike, target: number, tolerance = 1e-9): boolean {
  if (!map.unproject) return false;
  const ll = map.unproject(pixel);
  const elevation = readTerrainElevation(map, ll);
  if (elevation == null) return false;
  const m = projection.Mercator.fromLngLat(ll, elevation);
  const t = rayParameter(ray, [m.x, m.y, m.z]);
  return t >= 0 && t < target - tolerance;
}

/**
 * Refreshes height data without repeating a screen-space hit test. Fixed points
 * are geographic anchors: camera movement may improve their DEM value, but it
 * must never change their longitude, latitude, building, or known elevation.
 */
export function refreshMeasurementPointElevation(
  map: MapLibreMap,
  point: MeasurementPoint,
): MeasurementPoint {
  // Once acquired, a measurement is fixed in world space. Changing DEM LOD
  // during navigation must not rewrite known points or measured distances.
  if (point.elevationAvailable || (point.surface === 'building' && point.buildingHeightMeters == null)) return point;
  const terrainElevation = readTerrainElevation(map, [point.longitude, point.latitude]);
  if (terrainElevation == null) return point;

  return {
    ...point,
    elevationMeters: terrainElevation + (point.buildingHeightMeters ?? 0),
    elevationAvailable: true,
    surface: point.surface === 'building' ? 'building' : 'terrain',
  };
}

function queryBuilding(map: MapLibreMap, point: PointLike) {
  const [x, y] = Array.isArray(point) ? point : [point.x, point.y];
  const hitRadius = 7;
  const exactHit = map.queryRenderedFeatures(point, { layers: [BUILDINGS_LAYER_ID] })[0];
  if (exactHit) return exactHit;
  return map.queryRenderedFeatures(
    [[x - hitRadius, y - hitRadius], [x + hitRadius, y + hitRadius]],
    { layers: [BUILDINGS_LAYER_ID] },
  )[0];
}

export function measurementPointsEqual(a: MeasurementPoint[], b: MeasurementPoint[]): boolean {
  return a.length === b.length && a.every((point, index) => {
    const other = b[index];
    return point.id === other.id
      && point.longitude === other.longitude
      && point.latitude === other.latitude
      && point.elevationAvailable === other.elevationAvailable
      && point.surface === other.surface
      && Math.abs(point.elevationMeters - other.elevationMeters) < 0.01
      && point.buildingHeightMeters === other.buildingHeightMeters;
  });
}

function nextPointId(): string {
  pointSequence += 1;
  return `measurement-${Date.now()}-${pointSequence}`;
}
