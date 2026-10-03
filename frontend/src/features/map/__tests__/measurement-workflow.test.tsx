import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../../../App';
import type { MeasurementPoint, MeasurementState } from '../types/map';

const pointOne: MeasurementPoint = {
  id: 'point-1',
  longitude: 106.7,
  latitude: 10.8,
  elevationMeters: 8,
  elevationAvailable: true,
  surface: 'terrain',
};

const pointTwo: MeasurementPoint = {
  id: 'point-2',
  longitude: 106.7009,
  latitude: 10.8,
  elevationMeters: 28,
  elevationAvailable: true,
  surface: 'building',
  buildingHeightMeters: 20,
};

const pointWithoutElevation: MeasurementPoint = {
  id: 'point-without-elevation',
  longitude: 106.702,
  latitude: 10.801,
  elevationMeters: 0,
  elevationAvailable: false,
  surface: 'ground',
};

vi.mock('../components/UrbanMap', () => ({
  UrbanMap: ({ measurement, onMeasurementPoint }: {
    measurement: MeasurementState;
    onMeasurementPoint: (point: MeasurementPoint) => void;
  }) => (
    <div className="map-canvas" data-testid="mock-measurement-count">
      {measurement.points.length}
      <button type="button" onClick={() => onMeasurementPoint(pointOne)}>Add first point</button>
      <button type="button" onClick={() => onMeasurementPoint(pointTwo)}>Add second point</button>
      <button type="button" onClick={() => onMeasurementPoint(pointWithoutElevation)}>Add unavailable point</button>
    </div>
  ),
}));

describe('distance measurement workflow', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOONG_MAPTILES_KEY', 'test-map-key');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('keeps a multi-point measurement when switching between 2D and 3D', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Measure distance' }));
    await user.click(screen.getByRole('button', { name: 'Add first point' }));
    await user.click(screen.getByRole('button', { name: 'Add second point' }));

    const toolbar = screen.getByRole('region', { name: 'Distance measurement' });
    expect(within(toolbar).getByText('2 points')).toBeInTheDocument();
    expect(within(toolbar).getByText('Horizontal total')).toBeInTheDocument();
    expect(within(toolbar).getByText('Last segment')).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Done' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Switch to 3D' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('2');
    expect(within(toolbar).getByText('3D total')).toBeInTheDocument();

    await user.click(within(toolbar).getByRole('button', { name: 'Done' }));
    expect(within(toolbar).getByText('Measurement complete')).toBeInTheDocument();

    await user.click(within(toolbar).getByRole('button', { name: 'New measurement' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('0');
    expect(within(toolbar).getByText('Click the map to start')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Add first point' }));
    await user.click(screen.getByRole('button', { name: 'Add unavailable point' }));
    expect(within(toolbar).getByText('Elevation unavailable')).toBeInTheDocument();
  });
});
