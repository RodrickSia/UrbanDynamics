import { describe, expect, it } from 'vitest';

import type { MeasurementState } from '../types/map';
import { createMeasurementDistanceLabels } from '../utils/measurement';

const measurement: MeasurementState = {
  status: 'active',
  points: [
    { id: 'a', longitude: 106.7, latitude: 10.8, elevationMeters: 10, elevationAvailable: true, surface: 'terrain' },
    { id: 'b', longitude: 106.701, latitude: 10.8, elevationMeters: 30, elevationAvailable: true, surface: 'building' },
  ],
  preview: { id: 'preview', longitude: 106.702, latitude: 10.8, elevationMeters: 30, elevationAvailable: true, surface: 'building' },
};

describe('measurement distance labels', () => {
  it('creates stable labels for committed and preview segments', () => {
    const labels = createMeasurementDistanceLabels(measurement, '3d');

    expect(labels).toHaveLength(2);
    expect(labels[0]).toMatchObject({ id: 'a:b', preview: false });
    expect(labels[0].distanceMeters).toBeGreaterThan(labels[0].horizontalMeters);
    expect(labels[1]).toMatchObject({ id: 'b:preview', preview: true });
  });

  it('uses horizontal distance in 2D and reports unavailable 3D elevation honestly', () => {
    const unavailable: MeasurementState = {
      ...measurement,
      preview: null,
      points: [measurement.points[0], { ...measurement.points[1], elevationAvailable: false }],
    };

    expect(createMeasurementDistanceLabels(unavailable, '2d')[0].distanceMeters).toBeGreaterThan(0);
    expect(createMeasurementDistanceLabels(unavailable, '3d')[0].distanceMeters).toBeNull();
  });
});
