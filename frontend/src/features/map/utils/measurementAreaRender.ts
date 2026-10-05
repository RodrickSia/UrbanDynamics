import type { MapMode, MeasurementPoint } from '../types/map';
import { calculateAreaMeasurement } from './measurementArea';
import type { MeasurementRenderSegment } from './measurement';

export function createAreaRenderGeometry(points: MeasurementPoint[], mode: MapMode) {
  const area = calculateAreaMeasurement(points,mode);
  const vertices = area.valid ? area.vertices : points;
  const boundary: MeasurementRenderSegment[] = vertices.slice(1).map((p,i) => ({
    kind: 'area-boundary', start: [vertices[i].longitude,vertices[i].latitude], end: [p.longitude,p.latitude],
    startElevation: mode === '3d' ? vertices[i].elevationMeters : 0,
    endElevation: mode === '3d' ? p.elevationMeters : 0,
  }));
  if (vertices.length > 2) boundary.push({ kind:'area-boundary',
    start:[vertices.at(-1)!.longitude,vertices.at(-1)!.latitude], end:[vertices[0].longitude,vertices[0].latitude],
    startElevation: mode === '3d' ? vertices.at(-1)!.elevationMeters : 0,
    endElevation: mode === '3d' ? vertices[0].elevationMeters : 0 });
  const guides: MeasurementRenderSegment[] = [];
  if (area.valid && area.calculationMode === 'horizontal' && mode === '3d') {
    area.vertices.forEach((p,i) => {
      if (Math.abs(p.elevationMeters-points[i].elevationMeters) < 0.05) return;
      guides.push({ kind: 'area-boundary', start:[points[i].longitude,points[i].latitude],
        end:[p.longitude,p.latitude], startElevation:points[i].elevationMeters, endElevation:p.elevationMeters });
    });
  }
  const span = Math.max(1,...area.coordinates.flatMap(p => p.map(Math.abs)));
  // Physical grid spacing is frozen with the vertices, independent of zoom.
  const cellMeters = 2 ** Math.floor(Math.log2(span/8));
  return { area, boundary, guides, cellMeters };
}
