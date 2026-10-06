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
      async (input: string) =>
        new Response(
          JSON.stringify(
            input.endsWith('/population')
              ? {
                  available: true,
                  years: Array.from({ length: 16 }, (_, index) => ({ year: 2015 + index })),
                }
              : {
                  layers: [
                    { id: 'flood_history', available: true },
                    { id: 'flood_satellite', available: true },
                    { id: 'flood_risk', available: true },
                    { id: 'land_price', available: false },
                  ],
                },
          ),
        ),
    ),
  );
}
it('groups connected datasets separately from map display and keeps future integrations collapsed', async () => {
  mockCatalog();
  render(<Panel />);
  const datasets = await screen.findByRole('group', { name: 'Datasets' });
  await waitFor(() => expect(within(datasets).getByText('4 available')).toBeInTheDocument());
  expect(within(datasets).getByRole('checkbox', { name: 'Population' })).toBeEnabled();
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
