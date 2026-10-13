import { describe, expect, it } from 'vitest';
import { nearestSnap, snapSource } from './snapping';

const project = (position: number[]) => ({ x: position[0], y: position[1] });

describe('study-area snapping', () => {
  it('snaps to the closest edge of roads and polygon boundaries, or to a vertex', () => {
    const result = nearestSnap({ x: 5, y: 3 }, [
      { source: 'road-centerline', geometry: { type: 'LineString', coordinates: [[0, 0], [10, 0]] } },
      { source: 'parcel', geometry: { type: 'Polygon', coordinates: [[[0, 7], [10, 7], [10, 10], [0, 7]]] } },
    ], project);
    expect(result).toMatchObject({ coordinate: [5, 0], source: 'road-centerline', kind: 'edge' });
    expect(nearestSnap({ x: 0.1, y: 0.1 }, [{ source: 'water-polygon',
      geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 0]]] } }], project))
      .toMatchObject({ coordinate: [0, 0], kind: 'vertex' });
    expect(nearestSnap({ x: 5, y: 1 }, [{ source: 'road-polygon',
      geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 4], [0, 4], [0, 0]]] } }], project))
      .toMatchObject({ coordinate: [5, 0], source: 'road-polygon', kind: 'edge' });
  });
  it('does not snap beyond the screen radius', () => {
    expect(nearestSnap({ x: 50, y: 50 }, [{ source: 'road-polygon',
      geometry: { type: 'Polygon', coordinates: [[[0, 0], [10, 0], [10, 10], [0, 0]]] } }], project)).toBeNull();
  });
  it('classifies only the requested geometry sources', () => {
    expect(snapSource({ id: 'road-main', type: 'line', source: 'base' })).toBe('road-centerline');
    expect(snapSource({ id: 'road-area', type: 'fill', source: 'base' })).toBe('road-polygon');
    expect(snapSource({ id: 'river', type: 'fill', source: 'base' })).toBe('water-polygon');
    expect(snapSource({ id: 'building', type: 'fill', source: 'base' })).toBeNull();
  });
});
