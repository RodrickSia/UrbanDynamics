import { describe, expect, it } from 'vitest';
import type { MeasurementPoint, MeasurementEdge } from '../types/map';
import { createMeasurementSegments, createSnapHighlights, measurementVisualization, sharedMeasurementEdge } from '../utils/measurement';

const a: MeasurementPoint = { id: 'a', longitude: 106.7, latitude: 10.8,
  elevationMeters: 10, elevationAvailable: true, surface: 'building' };
const b: MeasurementPoint = { ...a, id: 'b', longitude: 106.7002, elevationMeters: 30 };
const edge: MeasurementEdge = { id: 'roof-edge', objectId: 'building-1',
  start: [a.longitude, a.latitude, 10], end: [b.longitude, b.latitude, 30] };

describe('contextual measurement', () => {
  it('keeps arbitrary measurements direct unless components are requested', () => {
    expect(createMeasurementSegments([a, b], '3d').map(s => s.kind)).toEqual(['distance']);
    expect(createMeasurementSegments([a, b], '3d', true).map(s => s.kind))
      .toEqual(['distance', 'horizontal', 'vertical']);
  });
  it('recognizes two vertices and a partial segment on the same real edge', () => {
    const start = { ...a, snap: { kind: 'vertex' as const, objectId: edge.objectId, primitiveId: 'v1', edges: [edge] } };
    const end = { ...b, snap: { kind: 'edge' as const, objectId: edge.objectId, primitiveId: edge.id, edges: [edge] } };
    expect(sharedMeasurementEdge(start, end)).toEqual(edge);
    expect(measurementVisualization(start, end, '3d', true)).toBe('edge');
    expect(createMeasurementSegments([start, end], '3d', true)).toHaveLength(1);
    expect(sharedMeasurementEdge(start, { ...end, snap: { ...end.snap, objectId: 'other' } })).toBeNull();
  });
  it('never creates degenerate or untrustworthy decomposition', () => {
    expect(measurementVisualization(a, { ...b, longitude: a.longitude }, '3d', true)).toBe('vertical-only');
    expect(measurementVisualization(a, { ...b, elevationMeters: a.elevationMeters }, '3d', true)).toBe('horizontal-only');
    expect(createMeasurementSegments([a, { ...b, elevationAvailable: false }], '3d', true)).toHaveLength(1);
    expect(createMeasurementSegments([a, b], '2d', true)).toHaveLength(1);
  });
  it('highlights the full underlying edge before the first click, without a measurement', () => {
    const preview = { ...a, longitude: 106.7001,
      snap: { kind: 'edge' as const, objectId: edge.objectId, primitiveId: edge.id, edges: [edge] } };
    const state = { status: 'active' as const, points: [], preview };
    expect(createMeasurementSegments([preview], '3d')).toHaveLength(0);
    expect(createSnapHighlights(state, '3d')).toEqual([{
      kind: 'edge-highlight', start: edge.start.slice(0,2), end: edge.end.slice(0,2),
      startElevation: edge.start[2], endElevation: edge.end[2],
    }]);
    expect(createSnapHighlights(state, '2d')).toHaveLength(0);
  });
});
