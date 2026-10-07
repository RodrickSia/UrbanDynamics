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
  UrbanMap: ({ measurement, onMeasurementPoint, poiEnabled }: {
    poiEnabled?: boolean;
    measurement: MeasurementState;
    onMeasurementPoint: (point: MeasurementPoint) => void;
  }) => (
    <div className="map-canvas" data-testid="mock-measurement-count">
      <span data-testid="poi-state">{String(poiEnabled)}</span>
      {measurement.points.length}
      <button type="button" onClick={() => onMeasurementPoint(pointOne)}>Add first point</button>
      <button type="button" onClick={() => onMeasurementPoint(pointTwo)}>Add second point</button>
      <button type="button" onClick={() => onMeasurementPoint({ ...pointOne, id:'third', latitude:10.8005 })}>Add third point</button>
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

  it('toggles POI independently and retains the choice across 2D/3D', async () => {
    const user=userEvent.setup();render(<App />);
    await user.click(screen.getByRole('button',{name:'Open data layers'}));
    const poi=screen.getByRole('checkbox',{name:'Points of interest'});
    expect(poi).toBeChecked();
    await user.click(poi);
    expect(screen.getByTestId('poi-state')).toHaveTextContent('false');
    await user.click(screen.getByRole('button',{name:'Switch to 3D'}));
    expect(screen.getByTestId('poi-state')).toHaveTextContent('false');
    await user.click(poi);
    expect(screen.getByTestId('poi-state')).toHaveTextContent('true');
  });

  it('keeps a multi-point measurement when switching between 2D and 3D', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Measurement tools' }));
    await user.click(await screen.findByRole('button', { name: 'Measure distance' }));
    await user.click(screen.getByRole('button', { name: 'Add first point' }));
    await user.click(screen.getByRole('button', { name: 'Add second point' }));

    const toolbar = screen.getByRole('region', { name: 'Distance measurement' });
    expect(within(toolbar).getByText('2 points')).toBeInTheDocument();
    expect(within(toolbar).queryByText('Horizontal total')).not.toBeInTheDocument();
    expect(within(toolbar).queryByText('Last segment')).not.toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Done' })).toBeEnabled();
    expect(within(toolbar).getByRole('button', { name: 'Clear measurement' }).querySelector('svg')?.getAttribute('class')).toMatch(/trash/i);

    await user.click(screen.getByRole('button', { name: 'Switch to 3D' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('2');
    expect(within(toolbar).queryByText('3D total')).not.toBeInTheDocument();
    const components = within(toolbar).getByRole('button', { name: 'Show distance components' });
    expect(components).toHaveAttribute('aria-pressed', 'false');
    await user.click(components);
    expect(components).toHaveAttribute('aria-pressed', 'true');

    await user.click(within(toolbar).getByRole('button', { name: 'Done' }));
    expect(within(toolbar).getByText('Measurement complete')).toBeInTheDocument();

    await user.click(within(toolbar).getByRole('button', { name: 'New measurement' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('0');
    expect(within(toolbar).getByText('Click the map to start')).toBeInTheDocument();
    expect(components).toHaveAttribute('aria-pressed', 'false');

    await user.click(screen.getByRole('button', { name: 'Add first point' }));
    await user.click(screen.getByRole('button', { name: 'Add unavailable point' }));
    expect(within(toolbar).getByText('Elevation unavailable')).toBeInTheDocument();
  });

  it('chooses area, requires a valid polygon, switches units and preserves it across map modes', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Measurement tools' }));
    await user.click(await screen.findByRole('button', { name: 'Measure area' }));
    const toolbar = await screen.findByRole('region', { name: 'Area measurement' });
    const done = within(toolbar).getByRole('button', { name:'Done' });
    expect(done).toBeDisabled();
    await user.click(screen.getByRole('button', { name:'Add first point' }));
    await user.click(screen.getByRole('button', { name:'Add second point' }));
    expect(done).toBeDisabled();
    await user.click(screen.getByRole('button', { name:'Add third point' }));
    expect(done).toBeEnabled();
    expect(within(toolbar).getByText('Horizontal projection')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name:'Switch to 3D' }));
    expect(within(toolbar).getByText('3D plane')).toBeInTheDocument();
    await user.selectOptions(within(toolbar).getByRole('combobox', { name:'Measurement units' }), 'imperial');
    expect(within(toolbar).getByText(/ft²|acre/)).toBeInTheDocument();
    expect(within(toolbar).getByText(/Perimeter .* ft/)).toBeInTheDocument();
    await user.click(done);
    expect(done).toBeDisabled();
    await user.click(screen.getByRole('button', { name:'Switch to 2D' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('3');
    await user.click(within(toolbar).getByRole('button', { name:'New measurement' }));
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('0');
    expect(within(toolbar).getByRole('combobox')).toHaveValue('imperial');
    await user.click(within(toolbar).getByRole('button', { name:'Clear measurement' }));
    expect(screen.queryByRole('region', { name:'Area measurement' })).not.toBeInTheDocument();
  });
  it('opens Viewshed as the third tool in 3D without deleting existing measurement anchors', async () => {
    const user=userEvent.setup();render(<App/>);
    await user.click(screen.getByRole('button',{name:'Measurement tools'}));
    await user.click(await screen.findByRole('button',{name:'Measure distance'}));
    await user.click(screen.getByRole('button',{name:'Add first point'}));
    await user.click(screen.getByRole('button',{name:'Add second point'}));
    await user.click(screen.getByRole('button',{name:'Measurement tools'}));
    await user.click(await screen.findByRole('button',{name:'Viewshed'}));
    expect(screen.getByRole('button',{name:'Switch to 2D'})).toBeInTheDocument();
    expect(screen.getByRole('region',{name:'Viewshed analysis'})).toHaveTextContent('place the observer');
    expect(screen.queryByRole('region',{name:'Distance measurement'})).not.toBeInTheDocument();
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('2');
    expect(screen.queryByRole('button',{name:'Done'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Delete selected viewshed'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'New'})).not.toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'Close viewshed editing'}));
    expect(screen.queryByRole('region',{name:'Viewshed analysis'})).not.toBeInTheDocument();
    expect(screen.getByRole('region',{name:'Distance measurement'})).toHaveTextContent('Measurement complete');
    expect(screen.getByTestId('mock-measurement-count')).toHaveTextContent('2');
  });
});
