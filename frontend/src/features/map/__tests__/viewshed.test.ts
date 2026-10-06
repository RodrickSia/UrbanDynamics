import { describe, expect, it } from 'vitest';
import {
  createViewshed,
  direction,
  frustumCorners,
  moveObserver,
  pointInFrustum,
  setDirection,
} from '../viewshed/math';
import { initialViewsheds, viewshedReducer } from '../viewshed/state';

const observer = { longitude: 106.7, latitude: 10.8, elevationMeters: 20 };
describe('world anchored viewshed', () => {
  it('keeps orientation independent of camera and separates observer height from target tilt', () => {
    const view = setDirection(createViewshed('a', observer), {
      heading: 90,
      tilt: 10,
      distance: 300,
    });
    expect(direction(view).heading).toBeCloseTo(90);
    expect(direction(view).tilt).toBeCloseTo(10);
    const raised = moveObserver(view, { ...observer, elevationMeters: 40 });
    expect(raised.target.elevationMeters - view.target.elevationMeters).toBeCloseTo(20);
    expect(direction(raised).tilt).toBeCloseTo(10);
    expect(view.observer).toEqual(observer);
  });
  it('clips by both FOV axes and distance rather than painting a cone indiscriminately', () => {
    const view = setDirection(createViewshed('a', observer), {
      heading: 0,
      tilt: 0,
      distance: 100,
    });
    expect(pointInFrustum(view, [0, 50, 0])).toBe(true);
    expect(pointInFrustum(view, [80, 50, 0])).toBe(false);
    expect(pointInFrustum(view, [0, 50, 80])).toBe(false);
    expect(pointInFrustum(view, [0, -10, 0])).toBe(false);
    expect(pointInFrustum(view, [0, 101, 0])).toBe(false);
    expect(frustumCorners(view)).toHaveLength(4);
  });
  it('previews after first click, retains on Done, and cancels only the unfinished object', () => {
    let state = viewshedReducer(initialViewsheds, { type: 'start' });
    state = viewshedReducer(state, { type: 'place', point: observer, id: 'a' });
    expect(state.phase).toBe('target');
    const target = { ...observer, latitude: 10.801 };
    state = viewshedReducer(state, { type: 'preview', point: target });
    expect(state.items[0].target).toEqual(target);
    state = viewshedReducer(state, { type: 'place', point: target, id: 'unused' });
    expect(state.phase).toBe('editing');
    state = viewshedReducer(state, { type: 'done' });
    expect(state.items).toHaveLength(1);
    expect(state.selectedId).toBeNull();
    state = viewshedReducer(state, { type: 'start' });
    state = viewshedReducer(state, { type: 'place', point: observer, id: 'b' });
    state = viewshedReducer(state, { type: 'cancel' });
    expect(state.items.map((v) => v.id)).toEqual(['a']);
    state = viewshedReducer(state, { type: 'select', id: 'a' });
    expect(state.phase).toBe('editing');
    state = viewshedReducer(state, { type: 'delete' });
    expect(state.items).toHaveLength(0);
  });
  it('discards an unfinished draft when selecting an existing analysis and bounds memory', () => {
    const items = Array.from({ length: 8 }, (_, i) => createViewshed(String(i), observer));
    const full = { items, selectedId: null, phase: 'idle' as const };
    const state = viewshedReducer(full, { type: 'start' });
    expect(state.phase).toBe('editing');
    expect(state.items).toHaveLength(8);
    const draft = { items: items.slice(0, 2), selectedId: '1', phase: 'target' as const };
    expect(viewshedReducer(draft, { type: 'select', id: '0' }).items.map((v) => v.id)).toEqual([
      '0',
    ]);
  });
});
