import { describe, it, expect } from 'vitest';
import { dragPoint } from '../viewshed/manipulators';

describe('viewshed world-axis manipulation', () => {
  it('intersects an XY plane and preserves its elevation', () => {
    expect(dragPoint([0, 0, 10], [20, 20, -10], [0, 0, 0], 'observer-xy')).toEqual([10, 10, 0]);
    expect(dragPoint([0, 0, 10], [20, 20, 10], [0, 0, 0], 'observer-xy')).toBeNull();
    expect(dragPoint([0, 0, 10], [20, 20, 20], [0, 0, 0], 'observer-xy')).toBeNull();
  });
  it('changes only the selected axis and rejects parallel/ill-conditioned rays', () => {
    expect(dragPoint([0, -10, 12], [0, 10, 12], [0, 0, 0], 'observer-z')).toEqual([0, 0, 12]);
    expect(dragPoint([3, -10, 0], [3, 10, 0], [0, 0, 0], 'heading', [1,0,0])).toEqual([3, 0, 0]);
    expect(dragPoint([0, 0, 0], [0, 0, 10], [0, 0, 5], 'tilt')).toBeNull();
  });
});
