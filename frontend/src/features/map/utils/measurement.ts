import type { MapMode, MeasurementPoint } from '../types/map';

const EARTH_RADIUS_METERS = 6_371_008.8;

export interface MeasurementSegmentMetrics {
  horizontalMeters: number;
  verticalMeters: number;
  spatialMeters: number;
}

export interface MeasurementSummary {
  segmentCount: number;
  totalHorizontalMeters: number;
  totalSpatialMeters: number;
  elevationAvailable: boolean;
  lastSegment: MeasurementSegmentMetrics | null;
}

export interface MeasurementRenderSegment {
  kind: 'distance' | 'horizontal' | 'vertical';
  start: [number, number];
  end: [number, number];
  startElevation: number;
  endElevation: number;
}

export function calculateHorizontalDistance(
  start: Pick<MeasurementPoint, 'longitude' | 'latitude'>,
  end: Pick<MeasurementPoint, 'longitude' | 'latitude'>,
): number {
  const latitude1 = toRadians(start.latitude);
  const latitude2 = toRadians(end.latitude);
  const latitudeDelta = toRadians(end.latitude - start.latitude);
  const longitudeDelta = toRadians(end.longitude - start.longitude);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(latitude1) * Math.cos(latitude2) * Math.sin(longitudeDelta / 2) ** 2;
  return EARTH_RADIUS_METERS * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

export function calculateMeasurementSummary(points: MeasurementPoint[]): MeasurementSummary {
  let totalHorizontalMeters = 0;
  let totalSpatialMeters = 0;
  let lastSegment: MeasurementSegmentMetrics | null = null;

  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1];
    const end = points[index];
    const horizontalMeters = calculateHorizontalDistance(start, end);
    const verticalMeters = start.elevationAvailable && end.elevationAvailable
      ? Math.abs(end.elevationMeters - start.elevationMeters)
      : 0;
    const spatialMeters = Math.hypot(horizontalMeters, verticalMeters);
    lastSegment = { horizontalMeters, verticalMeters, spatialMeters };
    totalHorizontalMeters += horizontalMeters;
    totalSpatialMeters += spatialMeters;
  }

  return {
    segmentCount: Math.max(0, points.length - 1),
    totalHorizontalMeters,
    totalSpatialMeters,
    elevationAvailable: points.length > 0 && points.every((point) => point.elevationAvailable),
    lastSegment,
  };
}

export function createMeasurementSegments(
  points: MeasurementPoint[],
  mode: MapMode,
): MeasurementRenderSegment[] {
  const segments: MeasurementRenderSegment[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1];
    const end = points[index];
    const startElevation = mode === '3d' ? start.elevationMeters : 0;
    const endElevation = mode === '3d' ? end.elevationMeters : 0;
    segments.push({
      kind: 'distance',
      start: [start.longitude, start.latitude],
      end: [end.longitude, end.latitude],
      startElevation,
      endElevation,
    });

    if (mode !== '3d') continue;
    segments.push({
      kind: 'horizontal',
      start: [start.longitude, start.latitude],
      end: [end.longitude, end.latitude],
      startElevation,
      endElevation: startElevation,
    });
    if (Math.abs(endElevation - startElevation) < 0.01) continue;
    segments.push({
      kind: 'vertical',
      start: [end.longitude, end.latitude],
      end: [end.longitude, end.latitude],
      startElevation,
      endElevation,
    });
  }
  return segments;
}

export function formatMeasurementDistance(meters: number): string {
  if (meters < 1_000) return `${Math.round(meters)} m`;
  return `${(meters / 1_000).toFixed(2)} km`;
}

function toRadians(value: number): number {
  return value * Math.PI / 180;
}
