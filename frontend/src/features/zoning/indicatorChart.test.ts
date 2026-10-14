import { describe, expect, it } from 'vitest';
import { difference, type Polygon } from 'polygon-clipping';
import { chartFeatures, chartRows } from './indicatorChart';
import type { AreaIndicators } from './areaIndicatorTypes';
import type { PolygonGeometry } from './types';

const geometry: PolygonGeometry = { type: 'Polygon', coordinates: [
  [[106.76,10.82],[106.764,10.82],[106.764,10.824],[106.76,10.824],[106.76,10.82]],
  [[106.761,10.821],[106.763,10.821],[106.763,10.823],[106.761,10.823],[106.761,10.821]],
] };
describe('area chart', () => {
  it('keeps missing values distinct from zero and preserves signed jobs balance', () => {
    const data = { baseline: { jobs_balance: null }, proposal: { jobs_balance: -25 } } as AreaIndicators;
    expect(chartRows(data, 'jobs_balance').map(row => row.value)).toEqual([null, -25]);
    const features = chartFeatures(geometry, chartRows(data, 'jobs_balance'));
    expect(features.features).toHaveLength(1);
    expect(features.features[0].properties?.label).toContain('-25');
    expect(features.features[0].properties?.height).toBeGreaterThan(0);
  });
  it('places bars inside concave or holed regions and uses one common scale', () => {
    const rows = [{ label: 'Existing', value: 50, unit: 'people', color: '#2877dc' },
      { label: 'Proposed', value: 100, unit: 'people', color: '#FF6D00' }];
    const result = chartFeatures(geometry, rows);
    expect(result.features).toHaveLength(2);
    for (const f of result.features) {
      expect(f.geometry.type).toBe('Polygon');
      if (f.geometry.type === 'Polygon') expect(difference(f.geometry.coordinates as Polygon, geometry.coordinates as Polygon)).toEqual([]);
    }
    expect(result.features[1].properties!.height).toBeCloseTo(result.features[0].properties!.height * 2);
  });
});
