export type Vec3 = [number, number, number];
export interface GeoPoint {
  longitude: number;
  latitude: number;
  elevationMeters: number;
}
export interface Viewshed {
  id: string;
  observer: GeoPoint;
  target: GeoPoint;
  horizontalFov: number;
  verticalFov: number;
}
export const MAX_DISTANCE = 2000;
const RAD = Math.PI / 180,
  CIRCUMFERENCE = 40075016.68557849;
export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const scale = (a: Vec3, n: number): Vec3 => [a[0] * n, a[1] * n, a[2] * n];
export const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const normalize = (a: Vec3): Vec3 => scale(a, 1 / (Math.hypot(...a) || 1));
export const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

/** Metric local Mercator frame: east, north, up. No screen/camera coordinates. */
export function frame(origin: GeoPoint) {
  const units = 1 / (CIRCUMFERENCE * Math.cos(origin.latitude * RAD));
  const merc = (p: GeoPoint): Vec3 => [
    (p.longitude + 180) / 360,
    (1 - Math.log(Math.tan(Math.PI / 4 + (p.latitude * RAD) / 2)) / Math.PI) / 2,
    p.elevationMeters * units,
  ];
  const anchor = merc(origin);
  const toLocal = (p: GeoPoint): Vec3 => {
    const m = merc(p);
    return [
      (m[0] - anchor[0]) / units,
      (anchor[1] - m[1]) / units,
      p.elevationMeters - origin.elevationMeters,
    ];
  };
  const toGeo = (p: Vec3): GeoPoint => ({
    longitude: (anchor[0] + p[0] * units) * 360 - 180,
    latitude: Math.atan(Math.sinh(Math.PI * (1 - 2 * (anchor[1] - p[1] * units)))) / RAD,
    elevationMeters: origin.elevationMeters + p[2],
  });
  return { anchor, units, toLocal, toGeo };
}
export function direction(view: Viewshed) {
  const target = frame(view.observer).toLocal(view.target);
  const distance = Math.max(1, Math.hypot(...target));
  const heading = (Math.atan2(target[0], target[1]) / RAD + 360) % 360;
  const tilt = Math.atan2(target[2], Math.hypot(target[0], target[1])) / RAD;
  const forward: Vec3 = [
    Math.sin(heading * RAD) * Math.cos(tilt * RAD),
    Math.cos(heading * RAD) * Math.cos(tilt * RAD),
    Math.sin(tilt * RAD),
  ];
  const right: Vec3 = [Math.cos(heading * RAD), -Math.sin(heading * RAD), 0];
  const up = cross(right, forward);
  return { heading, tilt, distance, forward, right, up };
}
export function setDirection(
  view: Viewshed,
  patch: Partial<{ heading: number; tilt: number; distance: number }>,
): Viewshed {
  const current = direction(view);
  const h = (Number.isFinite(patch.heading) ? patch.heading! : current.heading) * RAD;
  const t = clamp(Number.isFinite(patch.tilt) ? patch.tilt! : current.tilt, -89, 89) * RAD;
  const d = clamp(
    Number.isFinite(patch.distance) ? patch.distance! : current.distance,
    1,
    MAX_DISTANCE,
  );
  return {
    ...view,
    target: frame(view.observer).toGeo([
      Math.sin(h) * Math.cos(t) * d,
      Math.cos(h) * Math.cos(t) * d,
      Math.sin(t) * d,
    ]),
  };
}
export function createViewshed(id: string, observer: GeoPoint): Viewshed {
  return {
    id,
    observer,
    target: frame(observer).toGeo([0, 100, 0]),
    horizontalFov: 60,
    verticalFov: 45,
  };
}
export function moveObserver(view: Viewshed, observer: GeoPoint): Viewshed {
  return setDirection({ ...view, observer }, direction(view));
}
export function aimAt(view: Viewshed, target: GeoPoint): Viewshed {
  const next = { ...view, target };
  return direction(next).distance > MAX_DISTANCE
    ? setDirection(next, { distance: MAX_DISTANCE })
    : next;
}
export function frustumCorners(view: Viewshed): Vec3[] {
  const { forward, right, up, distance } = direction(view);
  const w = Math.tan((view.horizontalFov * RAD) / 2) * distance;
  const h = Math.tan((view.verticalFov * RAD) / 2) * distance;
  return [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ].map(([x, y]) => add(scale(forward, distance), add(scale(right, x * w), scale(up, y * h))));
}
export function pointInFrustum(view: Viewshed, p: Vec3): boolean {
  const { forward, right, up, distance } = direction(view),
    z = dot(p, forward);
  return (
    z >= 0.1 &&
    z <= distance &&
    Math.abs(dot(p, right)) <= z * Math.tan((view.horizontalFov * RAD) / 2) &&
    Math.abs(dot(p, up)) <= z * Math.tan((view.verticalFov * RAD) / 2)
  );
}
export function observerMatrix(view: Viewshed): Float32Array {
  const { forward: f, right: r, up: u, distance: far } = direction(view);
  const h = Math.tan((view.horizontalFov * RAD) / 2),
    v = Math.tan((view.verticalFov * RAD) / 2),
    near = 0.1;
  const a = (far + near) / (far - near),
    b = (-2 * far * near) / (far - near);
  return new Float32Array([
    r[0] / h,
    u[0] / v,
    a * f[0],
    f[0],
    r[1] / h,
    u[1] / v,
    a * f[1],
    f[1],
    r[2] / h,
    u[2] / v,
    a * f[2],
    f[2],
    0,
    0,
    b,
    0,
  ]);
}
export function sceneMatrix(camera: ArrayLike<number>, view: Viewshed): Float32Array {
  const { anchor, units } = frame(view.observer),
    result = new Float32Array(camera);
  for (let row = 0; row < 4; row++) {
    result[12 + row] =
      camera[row] * anchor[0] +
      camera[4 + row] * anchor[1] +
      camera[8 + row] * anchor[2] +
      camera[12 + row];
    result[row] *= units;
    result[4 + row] *= -units;
    result[8 + row] *= units;
  }
  return result;
}
