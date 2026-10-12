import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../../../App';

describe('map application shell', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOONG_MAPTILES_KEY', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('starts in 2D and keeps the 3D building layer synchronized with the mode', async () => {
    const user = userEvent.setup();
    render(<App />);

    const modeButton = screen.getByRole('button', { name: 'Switch to 3D' });
    expect(modeButton).toHaveAttribute('aria-pressed', 'false');

    await user.click(modeButton);
    await user.click(screen.getByRole('button', { name: 'Open data layers' }));

    expect(screen.getByRole('button', { name: 'Switch to 2D' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('checkbox', { name: '3D buildings' })).toBeChecked();
  });

  it('keeps the controls usable when the map key is missing', () => {
    render(<App />);

    expect(screen.getByRole('alert')).toHaveTextContent('Goong Map Tiles Key is not configured');
    expect(screen.getByRole('button', { name: 'Measurement tools' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Open time range' })).not.toBeInTheDocument();
  });
});
