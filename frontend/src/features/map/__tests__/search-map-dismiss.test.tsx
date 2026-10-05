import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../../../App';

vi.mock('../components/UrbanMap', () => ({
  UrbanMap: ({ onPointSelect }: { onPointSelect: (point: unknown) => void }) => (
    <div className="map-canvas">
      <button
        type="button"
        aria-label="Mock map surface"
        onClick={() =>
          onPointSelect({
            kind: 'point',
            longitude: 105.83,
            latitude: 21.03,
            zoom: 12,
            features: [],
          })
        }
      />
      <button
        type="button"
        aria-label="Mock named place"
        onClick={() =>
          onPointSelect({
            kind: 'point',
            longitude: 106.7,
            latitude: 10.8,
            zoom: 15,
            features: [
              { id: 'poi-1', label: 'Ben Thanh Market', layer: 'poi', isNamedPlace: true },
            ],
          })
        }
      />
    </div>
  ),
}));

describe('search dismissal on the map', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOONG_MAPTILES_KEY', 'test-map-key');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('uses the first map click only to close the open search workspace', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('searchbox', { name: 'Search places' }));
    expect(screen.getByRole('region', { name: 'Search workspace' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Mock map surface' }));

    expect(screen.queryByRole('region', { name: 'Search workspace' })).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'Place details' })).not.toBeInTheDocument();
  });

  it('toggles generic map details off on the next empty-map click', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Mock map surface' }));
    expect(screen.getByRole('complementary', { name: 'Place details' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Mock map surface' }));
    expect(screen.queryByRole('complementary', { name: 'Place details' })).not.toBeInTheDocument();
  });

  it('keeps place details open when the map click contains a named place', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Mock map surface' }));
    await user.click(screen.getByRole('button', { name: 'Mock named place' }));

    expect(screen.getByRole('heading', { name: 'Ben Thanh Market' })).toBeInTheDocument();
  });
});
