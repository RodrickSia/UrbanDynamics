import type { MapMode, MeasurementEdge, MeasurementPoint, MeasurementState } from '../types/map';

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
  kind: 'distance' | 'horizontal' | 'vertical' | 'edge-highlight' | 'area-boundary';
  start: [number, number];
  end: [number, number];
  startElevation: number;
  endElevation: number;
}

export interface MeasurementDistanceLabel {
  id: string;
  start: MeasurementPoint;
  end: MeasurementPoint;
  horizontalMeters: number;
  distanceMeters: number | null;
  preview: boolean;
  component?: 'H' | 'ΔZ';
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

export function createMeasurementDistanceLabels(
  measurement: MeasurementState,
  mode: MapMode,
): MeasurementDistanceLabel[] {
  const labels: MeasurementDistanceLabel[] = [];
  const append = (start: MeasurementPoint, end: MeasurementPoint, preview: boolean) => {
    const horizontalMeters = calculateHorizontalDistance(start, end);
    const elevationAvailable = start.elevationAvailable && end.elevationAvailable;
    const verticalMeters = elevationAvailable
      ? Math.abs(end.elevationMeters - start.elevationMeters)
      : 0;
    labels.push({
      id: `${start.id}:${preview ? 'preview' : end.id}`,
      start,
      end,
      horizontalMeters,
      distanceMeters: mode === '2d'
        ? horizontalMeters
        : elevationAvailable ? Math.hypot(horizontalMeters, verticalMeters) : null,
      preview,
    });
    if (measurementVisualization(start, end, mode, measurement.showComponents) === 'direct-horizontal-vertical') {
      const corner = { ...end, elevationMeters: start.elevationMeters };
      labels.push({ id: `${start.id}:${preview ? 'preview' : end.id}:horizontal`, start, end: corner,
        horizontalMeters, distanceMeters: horizontalMeters, preview, component: 'H' });
      labels.push({ id: `${start.id}:${preview ? 'preview' : end.id}:vertical`, start: corner, end,
        horizontalMeters: 0, distanceMeters: verticalMeters, preview, component: 'ΔZ' });
    }
  };

  for (let index = 1; index < measurement.points.length; index += 1) {
    append(measurement.points[index - 1], measurement.points[index], false);
  }
  if (measurement.status === 'active' && measurement.preview && measurement.points.length > 0) {
    append(measurement.points.at(-1)!, measurement.preview, true);
  }
  return labels;
}

export function createMeasurementSegments(
  points: MeasurementPoint[],
  mode: MapMode,
  showComponents = false,
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

    if (measurementVisualization(start, end, mode, showComponents) !== 'direct-horizontal-vertical') continue;
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
  if (meters < 1_000) return `${meters.toFixed(2)} m`;
  return `${(meters / 1_000).toFixed(2)} km`;
}

export type MeasurementVisualization = 'edge' | 'direct-only' | 'vertical-only'
  | 'horizontal-only' | 'direct-horizontal-vertical';

export function sharedMeasurementEdge(start: MeasurementPoint, end: MeasurementPoint): MeasurementEdge | null {
  if (!start.snap?.objectId || start.snap.objectId !== end.snap?.objectId) return null;
  return start.snap.edges?.find(edge => end.snap?.edges?.some(other => other.id === edge.id)) ?? null;
}

export function measurementVisualization(
  start: MeasurementPoint, end: MeasurementPoint, mode: MapMode, showComponents = false,
): MeasurementVisualization {
  if (mode === '2d') return 'horizontal-only';
  if (!start.elevationAvailable || !end.elevationAvailable) return 'direct-only';
  if (sharedMeasurementEdge(start, end)) return 'edge';
  if (calculateHorizontalDistance(start, end) < 0.02) return 'vertical-only';
  if (Math.abs(start.elevationMeters - end.elevationMeters) < 0.02) return 'horizontal-only';
  return showComponents ? 'direct-horizontal-vertical' : 'direct-only';
}

/** Geometry highlighting is independent of the measured A–B subsegment. */
export function createSnapHighlights(measurement: MeasurementState, mode: MapMode): MeasurementRenderSegment[] {
  if (mode !== '3d') return [];
  const edges = new Map<string, MeasurementEdge>();
  const points = measurement.status === 'active' && measurement.preview
    ? [...measurement.points, measurement.preview] : measurement.points;
  const hover = measurement.status === 'active' ? measurement.preview : null;
  if (hover?.snap?.kind === 'edge') {
    for (const edge of hover.snap.edges ?? []) edges.set(edge.id, edge);
  }
  const last = measurement.points.at(-1);
  if (measurement.status === 'active' && last?.snap?.kind === 'edge') {
    for (const edge of last.snap.edges ?? []) edges.set(edge.id, edge);
  }
  for (let index = 1; index < points.length; index++) {
    const edge = sharedMeasurementEdge(points[index - 1], points[index]);
    if (edge) edges.set(edge.id, edge);
  }
  return [...edges.values()].map(edge => ({ kind: 'edge-highlight',
    start: [edge.start[0], edge.start[1]], end: [edge.end[0], edge.end[1]],
    startElevation: edge.start[2], endElevation: edge.end[2] }));
}

export function measurementPhase(measurement: MeasurementState) {
  if (measurement.status === 'idle') return 'idle';
  if (measurement.status === 'complete') return 'completed';
  if (!measurement.points.length) return 'hovering';
  return measurement.preview ? 'preview' : 'start-selected';
}

function toRadians(value: number): number {
  return value * Math.PI / 180;
}
