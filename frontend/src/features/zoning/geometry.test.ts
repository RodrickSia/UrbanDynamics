import { describe, expect, it } from 'vitest';
import { editVertex, sketchGeometry } from './geometry';
import type { PolygonGeometry } from './types';

describe('zoning geometry edits', () => {
  it('preserves interior rings and unrelated multipolygon parts when editing a vertex', () => {
    const geometry: PolygonGeometry = { type: 'MultiPolygon', coordinates: [
      [[[0, 0], [4, 0], [4, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 1]]],
      [[[5, 5], [6, 5], [6, 6], [5, 5]]],
    ] };
    const updated = editVertex(geometry, 0, 0, [-1, 0]);
    expect(updated.coordinates[0][0][0]).toEqual([-1, 0]);
    expect(updated.coordinates[0][0].at(-1)).toEqual([-1, 0]);
    expect(updated.coordinates[0][1]).toEqual(geometry.coordinates[0][1]);
    expect(updated.coordinates[1]).toEqual(geometry.coordinates[1]);
    expect(geometry.coordinates[0][0][0]).toEqual([0, 0]);
  });
  it('adds/removes vertices while retaining a closed ring with at least three vertices', () => {
    const geometry: PolygonGeometry = { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 0]]] };
    expect(editVertex(geometry, 0, 0, null)).toEqual(geometry);
    const added = editVertex(geometry, 0, 0, [1, 0], true);
    expect(added.coordinates[0]).toEqual([[0, 0], [1, 0], [2, 0], [2, 2], [0, 0]]);
    expect(editVertex(added, 0, 1, null)).toEqual(geometry);
  });
  it('does not fabricate geometry for incomplete drawings', () => {
    expect(sketchGeometry({ tool: 'draw', points: [[0, 0], [1, 1]], geometry: null })).toBeNull();
    expect(sketchGeometry({ tool: 'split', points: [[0, 0], [1, 1]], geometry: null })?.type).toBe('LineString');
  });
});
