import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { LayerPanel } from '../components/LayerPanel';
import { useMapWorkspace } from '../hooks/useMapWorkspace';
import { useBackendLayers } from '../datasets/useBackendLayers';

function Panel() {
  const workspace = useMapWorkspace();
  const backend = useBackendLayers(workspace.layers);
  return (
    <LayerPanel
      backend={backend}
      layers={workspace.layers}
      opacityByLayer={workspace.opacityByLayer}
      onClose={() => undefined}
      onToggleLayer={workspace.handleLayerToggle}
      onOpacityChange={workspace.handleOpacityChange}
    />
  );
}
afterEach(() => vi.unstubAllGlobals());
function mockCatalog() {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (input: string) => {
        return new Response(
          JSON.stringify(
            input.endsWith('/population')
              ? {
                  available: true,
                  years: Array.from({ length: 16 }, (_, index) => ({ year: 2015 + index })),
                }
              : input.endsWith('/traffic/sumo-simulations/catalog')
                ? { available: true, network_input: true, network_edges: 1200, matched_observations: 4500 }
              : input.endsWith('/traffic/sumo-simulations/latest')
                ? {
                    run_id: 'a4b0baab-5b88-42e3-932d-72a8103fe870',
                    weekday: 1,
                    period: '08:00',
                    metadata: { features: 420, max_estimated_cars_6h: 120 },
                  }
              : input.includes('/traffic/sumo-simulations/runs/')
                ? { status: 'completed', metadata: { features: 420, max_estimated_cars_6h: 120 } }
              : input.endsWith('/traffic/catalog')
                ? { available: true, network_available: true }
              : {
                  layers: [
                    { id: 'flood_history', available: true },
                    { id: 'flood_satellite', available: true },
                    { id: 'flood_risk', available: true },
                    { id: 'land_price', available: false },
                  ],
                },
          ),
        );
      },
    ),
  );
}
it('groups connected datasets separately from map display and keeps future integrations collapsed', async () => {
  mockCatalog();
  render(<Panel />);
  const datasets = await screen.findByRole('group', { name: 'Datasets' });
  await waitFor(() => expect(within(datasets).getByText('7 available')).toBeInTheDocument());
  expect(within(datasets).getByRole('checkbox', { name: 'Population' })).toBeEnabled();
  expect(within(datasets).getByRole('checkbox', { name: 'Traffic congestion prediction (historical)' })).toBeEnabled();
  expect(within(datasets).getByRole('checkbox', { name: 'SUMO road network' })).toBeEnabled();
  expect(within(datasets).getByRole('checkbox', { name: 'SUMO congestion simulation' })).toBeEnabled();
  expect(within(datasets).queryByText('WorldPop · 16 years')).not.toBeInTheDocument();
  expect(within(datasets).queryByText('Ready')).not.toBeInTheDocument();
  expect(screen.queryByText('Building extrusions')).not.toBeInTheDocument();
  expect(within(datasets).getByRole('checkbox', { name: 'Land price' })).toBeDisabled();
  expect(
    within(screen.getByRole('group', { name: 'Map display' })).getByRole('checkbox', {
      name: 'Points of interest',
    }),
  ).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Rain' })).not.toBeVisible();
  await userEvent.click(screen.getByText('More layers'));
  expect(screen.getByRole('checkbox', { name: 'Rain' })).toBeDisabled();
});
it('lets users display historical traffic and the SUMO road graph when the API reports them available', async () => {
  mockCatalog();
  render(<Panel />);
  const traffic = await screen.findByRole('checkbox', { name: 'Traffic congestion prediction (historical)' });
  await waitFor(() => expect(traffic).toBeEnabled());

  await userEvent.click(traffic);
  expect(traffic).toBeChecked();
  expect(screen.getByRole('combobox', { name: 'Traffic prediction day of week' })).toBeInTheDocument();
  expect(screen.getByLabelText('Traffic prediction time of day')).toBeInTheDocument();
  expect(screen.getByRole('group', { name: 'Historical congestion score from 0 to 100' })).toBeInTheDocument();
  expect(screen.getByText('Estimated congestion score · low to high')).toBeInTheDocument();
  expect(screen.queryByText('A', { selector: '.dataset-legend-item' })).not.toBeInTheDocument();

  const sumo = screen.getByRole('checkbox', { name: 'SUMO road network' });
  await userEvent.click(sumo);
  expect(sumo).toBeChecked();
  expect(screen.getByText('SUMO network edge')).toBeInTheDocument();
});
it('shows the latest cached SUMO result as a data layer without submitting a run', async () => {
  mockCatalog();
  render(<Panel />);
  const simulation = await screen.findByRole('checkbox', { name: 'SUMO congestion simulation' });
  await waitFor(() => expect(simulation).toBeEnabled());
  await userEvent.click(simulation);
  await waitFor(() => expect(screen.getByText(/Latest precomputed scenario/)).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: /run .*SUMO/i })).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
  expect(screen.getByRole('group', { name: 'Estimated car passages per road over six hours' })).toBeInTheDocument();
  expect(screen.getByText('120')).toBeInTheDocument();
});
it('reveals compact controls only for active layers and supports keyboard toggling', async () => {
  mockCatalog();
  render(<Panel />);
  const population = await screen.findByRole('checkbox', { name: 'Population' });
  await waitFor(() => expect(population).toBeEnabled());
  expect(screen.queryByRole('combobox', { name: 'Population year' })).not.toBeInTheDocument();
  population.focus();
  await userEvent.keyboard(' ');
  expect(population).toBeChecked();
  expect(screen.getByRole('combobox', { name: 'Population year' })).toHaveValue('2026');
  expect(screen.getByText('1 active')).toBeInTheDocument();
  expect(screen.getByLabelText('Population legend')).toBeInTheDocument();
  population.focus();
  await userEvent.keyboard(' ');
  expect(screen.queryByRole('combobox', { name: 'Population year' })).not.toBeInTheDocument();
});
it('shows disconnected catalogs honestly without disabling local display controls', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
  render(<Panel />);
  await waitFor(() =>
    expect(screen.getByText('Could not connect to data sources')).toBeInTheDocument(),
  );
  expect(screen.getByRole('button', { name: 'Refresh data sources' })).toBeEnabled();
  expect(screen.getByRole('checkbox', { name: 'Population' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: 'Points of interest' })).toBeEnabled();
});
