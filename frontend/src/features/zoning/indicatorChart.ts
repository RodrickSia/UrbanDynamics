import type { FeatureCollection } from 'geojson';
import { indicatorMetrics, type AreaIndicators } from './areaIndicatorTypes';
import { pointInArea } from './developmentGeometry';
import { rings } from './geometry';
import type { PolygonGeometry } from './types';

export type ChartMetric = typeof indicatorMetrics[number][0] | 'land_use' | 'zoning' | 'transit';
export interface ChartRow { label: string; value: number | null; unit: string; color: string }
export interface IndicatorChart { scope: string; geometry: PolygonGeometry; metric: ChartMetric; rows: ChartRow[] }
export const chartMetrics = [...indicatorMetrics.map(([id, label]) => [id, label] as const),
  ['land_use', 'Land use'], ['zoning', 'Zoning'], ['transit', 'Transit access']] as const;
export const chartValue = (row: ChartRow) => row.value === null ? 'No data' : `${row.value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${row.unit}`;

export function chartRows(data: AreaIndicators, metric: ChartMetric): ChartRow[] {
  if (metric === 'land_use' || metric === 'zoning') return (data[metric] ?? []).map(row => ({
    label: row.code ? `${row.code} · ${row.label}` : row.label, value: row.percent, unit: '%', color: row.color }));
  if (metric === 'transit') return [{ label: 'Transit access', value: data.transit.coverage_percent, unit: '%', color: '#79ABA5' }];
  const unit = indicatorMetrics.find(([id]) => id === metric)![2];
  return [{ label: 'Existing', value: data.baseline[metric], unit, color: '#2877dc' },
    ...(data.proposal ? [{ label: 'Proposed', value: data.proposal[metric], unit, color: '#FF6D00' }] : [])];
}

/** Aggregate chart, not a spatial allocation. Find a clear interior anchor including holes. */
export function chartFeatures(area: PolygonGeometry, rows: ChartRow[]): FeatureCollection {
  const points = rings(area).flat();
  const x0 = Math.min(...points.map(p => p[0])), x1 = Math.max(...points.map(p => p[0]));
  const y0 = Math.min(...points.map(p => p[1])), y1 = Math.max(...points.map(p => p[1]));
  const cos = Math.cos((y0 + y1) * Math.PI / 360);
  let anchor = [x0, y0], radius = 0;
  const edges = rings(area).flatMap(r => r.slice(1).map((b, i) => [r[i], b]));
  for (let i = 0; i < 17; i++) for (let j = 0; j < 17; j++) {
    const p = [x0 + (x1-x0)*(i+.5)/17, y0 + (y1-y0)*(j+.5)/17];
    if (!pointInArea(p, area)) continue;
    let distance = Infinity;
    for (const [a,b] of edges) {
      const dx = (b[0]-a[0])*cos, dy = b[1]-a[1];
      const px = (p[0]-a[0])*cos, py = p[1]-a[1];
      const t = Math.max(0, Math.min(1, (px*dx+py*dy)/(dx*dx+dy*dy || 1)));
      distance = Math.min(distance, Math.hypot(px-t*dx, py-t*dy));
    }
    if (distance > radius) { radius = distance; anchor = p; }
  }
  const available = rows.filter(r => r.value !== null && Number.isFinite(r.value));
  if (!radius || !available.length) return { type: 'FeatureCollection', features: [] };
  const max = rows.every(r => r.unit === '%') ? 100 : Math.max(...available.map(r => Math.abs(r.value!)), 1);
  const columns = Math.ceil(Math.sqrt(available.length)), countY = Math.ceil(available.length / columns);
  const step = radius / Math.max(columns, countY), width = step * .72;
  const top = Math.max(20, Math.min(180, radius * 111320));
  return { type: 'FeatureCollection', features: available.map((row, index) => {
    const x = anchor[0] + (index % columns - (columns-1)/2)*step/cos;
    const y = anchor[1] + (Math.floor(index/columns) - (countY-1)/2)*step;
    const dx = width/2/cos, dy = width/2;
    return { type: 'Feature', id: index, properties: {
      label: `${row.label} · ${chartValue(row)}`, color: row.value! < 0 ? '#b54e44' : row.color,
      height: Math.abs(row.value!)/max*top,
    }, geometry: { type: 'Polygon', coordinates: [[[x-dx,y-dy],[x+dx,y-dy],[x+dx,y+dy],[x-dx,y+dy],[x-dx,y-dy]]] } };
  }) };
}
