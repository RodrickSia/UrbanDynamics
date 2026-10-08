import { add, dot, scale, direction, clamp, setDirection, type Vec3, type Viewshed } from './math';

export type ViewshedHandle =
  | 'observer-xy'
  | 'observer-z'
  | 'heading'
  | 'tilt'
  | 'distance'
  | 'fov-left'
  | 'fov-right'
  | 'fov-top'
  | 'fov-bottom';

export function handleAxis(view: Viewshed, handle: ViewshedHandle): Vec3 {
  const d = direction(view);
  if (handle === 'heading' || handle === 'fov-left' || handle === 'fov-right') return d.right;
  if (handle === 'tilt' || handle === 'fov-top' || handle === 'fov-bottom') return d.up;
  if (handle === 'distance') return d.forward;
  return [0, 0, 1];
}

/** Snapshot-relative edits: rotating one degree of freedom never changes range. */
export function adjustHandle(view: Viewshed, handle: ViewshedHandle, delta: Vec3): Viewshed {
  const d = direction(view),
    amount = dot(delta, handleAxis(view, handle));
  const degrees = (radians: number) => (radians * 180) / Math.PI;
  if (handle === 'heading')
    return setDirection(view, {
      heading:
        d.heading +
        degrees(
          Math.atan2(amount, Math.max(0.01, d.distance * Math.cos((d.tilt * Math.PI) / 180))),
        ),
    });
  if (handle === 'tilt')
    return setDirection(view, {
      tilt: d.tilt + degrees(Math.atan2(amount, d.distance)),
    });
  if (handle === 'distance') return setDirection(view, { distance: d.distance + amount });
  const horizontal = handle === 'fov-left' || handle === 'fov-right';
  const sign = handle === 'fov-left' || handle === 'fov-bottom' ? -1 : 1;
  const initial = horizontal ? view.horizontalFov : view.verticalFov;
  const halfExtent = Math.tan((initial * Math.PI) / 360) * d.distance + sign * amount;
  const angle = clamp(degrees(2 * Math.atan2(halfExtent, d.distance)), 5, 120);
  return handle.startsWith('fov-')
    ? { ...view, [horizontal ? 'horizontalFov' : 'verticalFov']: angle }
    : view;
}

/** Closest ray/axis point, or intersection with the observer's horizontal plane. */
export function dragPoint(
  near: Vec3,
  far: Vec3,
  origin: Vec3,
  handle: ViewshedHandle,
  axis: Vec3 = [0, 0, 1],
): Vec3 | null {
  const ray = add(far, scale(near, -1));
  if (handle === 'observer-xy') {
    if (Math.abs(ray[2]) < 1e-8) return null;
    const t = (origin[2] - near[2]) / ray[2];
    return t < 0 ? null : add(near, scale(ray, t));
  }
  const delta = add(near, scale(origin, -1)),
    a = dot(ray, ray),
    b = dot(ray, axis),
    denominator = a - b * b;
  if (denominator < 1e-10) return null;
  return add(origin, scale(axis, (a * dot(delta, axis) - b * dot(delta, ray)) / denominator));
}
