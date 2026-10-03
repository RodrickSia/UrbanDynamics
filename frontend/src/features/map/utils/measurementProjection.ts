import type { MercatorCoordinate, PointLike } from 'maplibre-gl';

export type Position3 = [number, number, number];
export interface MeasurementRay { near: Position3; far: Position3 }
export interface ProjectedMeasurementPosition { x: number; y: number; visible: boolean }

/** Shared camera snapshot from the actual custom-layer render, in double precision. */
export class MeasurementProjection {
  matrix: number[] | null = null;
  private cameraMatrix: DOMMatrix | null = null;
  private inverseMatrix: DOMMatrix | null = null;

  constructor(readonly Mercator: typeof MercatorCoordinate) {}

  update(matrix: ArrayLike<number>): void {
    if (this.matrix?.every((v, i) => v === matrix[i])) return;
    this.matrix = Array.from(matrix);
    this.cameraMatrix = null;
    this.inverseMatrix = null;
  }

  ray(point: PointLike, width: number, height: number): MeasurementRay | null {
    if (!this.matrix || !width || !height) return null;
    const [x, y] = Array.isArray(point) ? point : [point.x, point.y];
    const inverse = this.inverseMatrix ??= new DOMMatrix(this.matrix).inverse();
    const unproject = (z: number): Position3 => {
      const p = inverse.transformPoint({ x: x / width * 2 - 1, y: 1 - y / height * 2, z });
      return [p.x / p.w, p.y / p.w, p.z / p.w];
    };
    const near = unproject(-1);
    const far = unproject(1);
    return [...near, ...far].every(Number.isFinite) ? { near, far } : null;
  }

  project(position: Position3, width: number, height: number): ProjectedMeasurementPosition | null {
    if (!this.matrix || !width || !height) return null;
    const camera = this.cameraMatrix ??= new DOMMatrix(this.matrix);
    const clip = camera.transformPoint({
      x: position[0], y: position[1], z: position[2], w: 1,
    });
    if (![clip.x, clip.y, clip.z, clip.w].every(Number.isFinite) || clip.w <= 0) return null;
    const x = (clip.x / clip.w + 1) * width / 2;
    const y = (1 - clip.y / clip.w) * height / 2;
    return {
      x,
      y,
      visible: clip.z >= -clip.w && clip.z <= clip.w
        && x >= 0 && x <= width && y >= 0 && y <= height,
    };
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
