import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { DatasetLinePreview } from '../datasets/BackendDataScene';
import { LAND_PRICE_LAYER } from '../layers/landPrice';

describe('land-price road preview', () => {
  it('shows all three published price categories, including a missing value', () => {
    const map = { getContainer: () => ({ clientWidth: 900, clientHeight: 600 }) } as MapLibreMap;
    render(<DatasetLinePreview map={map} hover={{ layer: LAND_PRICE_LAYER, x: 100, y: 100,
      properties: { road: 'Đường số 410', residential_vnd_m2: 55_100_000,
        commercial_vnd_m2: 33_100_000, other_nonagricultural_vnd_m2: null } }} />);

    const tooltip = screen.getByRole('tooltip', { name: 'Land price road details' });
    expect(within(tooltip).getByText('Residential')).toBeInTheDocument();
    expect(within(tooltip).getByText('Commercial')).toBeInTheDocument();
    expect(within(tooltip).getByText('Other non-agricultural')).toBeInTheDocument();
    expect(within(tooltip).getByText('Unavailable')).toBeInTheDocument();
  });
});
