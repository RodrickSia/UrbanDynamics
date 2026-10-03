import type { LngLatLike, Map as MapLibreMap, MapGeoJSONFeature, PointLike } from 'maplibre-gl';

import { BUILDINGS_LAYER_ID } from '../layers/buildings3d';
import type { MapMode, MeasurementPoint } from '../types/map';
import type { MeasurementProjection } from './measurementProjection';
import { pickBuildingSurface } from './measurementPicking';
import { readTerrainElevation } from './terrainElevation';

const BUILDING_HEIGHT_KEYS = ['max_height', 'height', 'render_height', 'building:height'] as const;
const buildingCandidates = new WeakMap<MapLibreMap, MapGeoJSONFeature[]>();
let pointSequence = 0;

export function invalidateMeasurementPicking(map: MapLibreMap): void {
  buildingCandidates.delete(map);
}

export function readBuildingHeight(properties: Record<string, unknown> | null | undefined): number | null {
  if (!properties) return null;
  for (const key of BUILDING_HEIGHT_KEYS) {
    if (properties[key] == null || properties[key] === '') continue;
    const value = Number(properties[key]);
    if (!Number.isFinite(value) || value < 0) continue;
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
): MeasurementPoint {
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
    } else {
      building = queryBuilding(map, queryPoint);
    }
  }
  const buildingHeight = readBuildingHeight(building?.properties);
  const anchoredCoordinate = surfaceHit?.coordinate ?? clickedCoordinate;
  const lngLat: LngLatLike = anchoredCoordinate;
  const terrainElevation = mode === '3d' ? readTerrainElevation(map, lngLat) : null;
  const groundElevation = terrainElevation ?? 0;
  if (building && buildingHeight != null && surfaceHit?.groundElevation != null) {
    return {
      id: id ?? nextPointId(),
      longitude: anchoredCoordinate[0],
      latitude: anchoredCoordinate[1],
      elevationMeters: surfaceHit.elevation,
      elevationAvailable: true,
      surface: 'building',
      buildingHeightMeters: surfaceHit.heightAboveGround,
    };
  }

  return {
    id: id ?? nextPointId(),
    longitude: anchoredCoordinate[0],
    latitude: anchoredCoordinate[1],
    elevationMeters: groundElevation,
    elevationAvailable: terrainElevation != null && !building,
    surface: building ? 'building' : terrainElevation != null ? 'terrain' : 'ground',
    ...(surfaceHit && buildingHeight != null ? { buildingHeightMeters: surfaceHit.heightAboveGround } : {}),
  };
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
