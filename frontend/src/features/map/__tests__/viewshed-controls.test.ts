import { expect, it } from 'vitest';
import { createViewshed, direction, setDirection, scale } from '../viewshed/math';
import { adjustHandle } from '../viewshed/manipulators';

const view = setDirection(
  createViewshed('v', {
    longitude: 106.7,
    latitude: 10.8,
    elevationMeters: 80,
  }),
  { heading: 35, tilt: 25, distance: 150 },
);
it('heading and tilt drags preserve range and the other angle', () => {
  const d = direction(view);
  const h = direction(adjustHandle(view, 'heading', scale(d.right, 30)));
  expect(h.heading).toBeGreaterThan(d.heading);
  expect(h.tilt).toBeCloseTo(d.tilt, 5);
  expect(h.distance).toBeCloseTo(d.distance, 5);
  const t = direction(adjustHandle(view, 'tilt', scale(d.up, 30)));
  expect(t.tilt).toBeGreaterThan(d.tilt);
  expect(t.heading).toBeCloseTo(d.heading, 5);
  expect(t.distance).toBeCloseTo(d.distance, 5);
  const r = direction(adjustHandle(view, 'distance', scale(d.forward, 30)));
  expect(r.distance).toBeCloseTo(180, 5);
  expect(r.heading).toBeCloseTo(d.heading, 5);
  expect(r.tilt).toBeCloseTo(d.tilt, 5);
});
it('four FOV edges resize symmetrically without moving observer or target', () => {
  const d = direction(view);
  for (const [handle, delta] of [
    ['fov-left', scale(d.right, -20)],
    ['fov-right', scale(d.right, 20)],
    ['fov-top', scale(d.up, 20)],
    ['fov-bottom', scale(d.up, -20)],
  ] as const) {
    const next = adjustHandle(view, handle, delta);
    expect(next.observer).toEqual(view.observer);
    expect(next.target).toEqual(view.target);
    expect(
      handle === 'fov-left' || handle === 'fov-right' ? next.horizontalFov : next.verticalFov,
    ).toBeGreaterThan(
      handle === 'fov-left' || handle === 'fov-right' ? view.horizontalFov : view.verticalFov,
    );
  }
  expect(adjustHandle(view, 'fov-left', scale(d.right, 10000)).horizontalFov).toBe(5);
  expect(adjustHandle(view, 'fov-top', scale(d.up, 10000)).verticalFov).toBe(120);
});
