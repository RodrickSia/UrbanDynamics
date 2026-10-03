import type { MercatorCoordinate, PointLike } from 'maplibre-gl';

export type Position3 = [number, number, number];
export interface MeasurementRay { near: Position3; far: Position3 }

/** Shared camera snapshot from the actual custom-layer render, in double precision. */
export class MeasurementProjection {
  matrix: number[] | null = null;

  constructor(readonly Mercator: typeof MercatorCoordinate) {}

  update(matrix: ArrayLike<number>): void {
    this.matrix = Array.from(matrix);
  }

  ray(point: PointLike, width: number, height: number): MeasurementRay | null {
    if (!this.matrix || !width || !height) return null;
    const [x, y] = Array.isArray(point) ? point : [point.x, point.y];
    const inverse = new DOMMatrix(this.matrix).inverse();
    const unproject = (z: number): Position3 => {
      const p = inverse.transformPoint({ x: x / width * 2 - 1, y: 1 - y / height * 2, z });
      return [p.x / p.w, p.y / p.w, p.z / p.w];
    };
    const near = unproject(-1);
    const far = unproject(1);
    return [...near, ...far].every(Number.isFinite) ? { near, far } : null;
  }
}

/** Multiply by the local origin BEFORE converting to GPU float32. */
export function localProjectionMatrix(matrix: ArrayLike<number>, origin: Position3): Float32Array {
  const result = new Float32Array(matrix);
  for (let row = 0; row < 4; row += 1) {
    result[12 + row] = matrix[row] * origin[0]
      + matrix[4 + row] * origin[1] + matrix[8 + row] * origin[2] + matrix[12 + row];
  }
  return result;
}
