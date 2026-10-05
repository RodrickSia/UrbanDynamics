import type { MeasurementPoint } from '../types/map';

export type Vector3 = [number, number, number];
export type GeographicPosition = Pick<MeasurementPoint, 'longitude' | 'latitude' | 'elevationMeters'>;
const A = 6_378_137;
const E2 = 6.6943799901413165e-3;
const RAD = Math.PI / 180;
export const dot = (a: Vector3, b: Vector3) => a.reduce((sum, v, i) => sum + v * b[i], 0);
export const subtract = (a: Vector3, b: Vector3): Vector3 => [a[0]-b[0], a[1]-b[1], a[2]-b[2]];
export const cross = (a: Vector3, b: Vector3): Vector3 => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
export const normalize = (v: Vector3): Vector3 => v.map(x => x / Math.hypot(...v)) as Vector3;

function ecef(p: GeographicPosition): Vector3 {
  const lat = p.latitude * RAD, lng = p.longitude * RAD;
  const n = A / Math.sqrt(1 - E2 * Math.sin(lat) ** 2);
  return [(n+p.elevationMeters)*Math.cos(lat)*Math.cos(lng),
    (n+p.elevationMeters)*Math.cos(lat)*Math.sin(lng), (n*(1-E2)+p.elevationMeters)*Math.sin(lat)];
}

/** Double-precision WGS84 local East/North/Up frame. No map zoom or screen pixels. */
export function createAreaFrame(origin: GeographicPosition) {
  const center = ecef(origin), lat = origin.latitude * RAD, lng = origin.longitude * RAD;
  const axes: Vector3[] = [[-Math.sin(lng), Math.cos(lng), 0],
    [-Math.sin(lat)*Math.cos(lng), -Math.sin(lat)*Math.sin(lng), Math.cos(lat)],
    [Math.cos(lat)*Math.cos(lng), Math.cos(lat)*Math.sin(lng), Math.sin(lat)]];
  return {
    toLocal(p: GeographicPosition): Vector3 {
      const delta = subtract(ecef(p), center);
      return axes.map(axis => dot(delta, axis)) as Vector3;
    },
    toGeographic(local: Vector3): GeographicPosition {
      const [x,y,z] = center.map((v,i) => v + local.reduce((sum, t, j) => sum + t * axes[j][i], 0));
      const radius = Math.hypot(x,y);
      let latitude = Math.atan2(z, radius*(1-E2));
      for (let i = 0; i < 8; i++) {
        const n = A / Math.sqrt(1-E2*Math.sin(latitude)**2);
        latitude = Math.atan2(z + E2*n*Math.sin(latitude), radius);
      }
      const n = A / Math.sqrt(1-E2*Math.sin(latitude)**2);
      return { longitude: Math.atan2(y,x)/RAD, latitude: latitude/RAD,
        elevationMeters: radius/Math.cos(latitude)-n };
    },
  };
}
