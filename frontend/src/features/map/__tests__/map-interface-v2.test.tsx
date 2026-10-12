import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../../../App';
import { gsap } from '../motion';

describe('map-first workspace', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOONG_MAPTILES_KEY', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('removes product chrome and keeps search collapsed in the top-left', () => {
    render(<App />);

    expect(document.querySelector('.app-shell')).toHaveClass('theme-light');
    expect(screen.queryByText('UrbanDynamics')).not.toBeInTheDocument();
    expect(screen.queryByText('All Vietnam')).not.toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: 'Search places' })).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Search workspace' })).not.toBeInTheDocument();
    expect(document.querySelector('.map-status')).not.toBeInTheDocument();
  });

  it('opens contextual search content, dismisses it outside, and opens place details on selection', async () => {
    const user = userEvent.setup();
    render(<App />);

    const search = screen.getByRole('searchbox', { name: 'Search places' });
    await user.click(search);

    const searchWorkspace = screen.getByRole('region', { name: 'Search workspace' });
    expect(within(searchWorkspace).getByText('Recent')).toBeInTheDocument();
    expect(within(searchWorkspace).getByText('This area')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(screen.queryByRole('region', { name: 'Search workspace' })).not.toBeInTheDocument();

    await user.click(search);
    await user.click(await screen.findByRole('button', { name: 'Hanoi, Vietnam' }));

    expect(screen.queryByRole('region', { name: 'Search workspace' })).not.toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Place details' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse place details' })).toBeEnabled();
  });

  it('keeps the map tool cluster focused on active tools', () => {
    render(<App />);

    expect(screen.queryByRole('region', { name: 'Time range' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open time range' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Measurement tools' })).toBeEnabled();
  });

  it('uses the right sidebar for layers and a compact bottom toolbar for distance measurement', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Open data layers' }));
    expect(screen.getByRole('region', { name: 'Data layers' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Measurement tools' }));
    await user.click(await screen.findByRole('button', { name: 'Measure distance' }));
    expect(screen.queryByRole('region', { name: 'Data layers' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Distance measurement' })).toHaveClass('measurement-toolbar');
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'New measurement' })).toBeEnabled();
    expect(screen.getByTestId('navigation-cluster')).toHaveAttribute('data-right-panel-open', 'false');
    expect(screen.queryByText('Spatial tools')).not.toBeInTheDocument();
    expect(screen.queryByText('Draw research area')).not.toBeInTheDocument();
    expect(screen.queryByText(/Select 3 more points/i)).not.toBeInTheDocument();
  });

  it('shows a single text mode control that changes from 2D to 3D', async () => {
    const user = userEvent.setup();
    const animation = vi.spyOn(gsap, 'fromTo');
    render(<App />);

    const switchTo3d = screen.getByRole('button', { name: 'Switch to 3D' });
    expect(switchTo3d).toHaveAttribute('aria-pressed', 'false');
    expect(switchTo3d).toHaveTextContent('2D');

    await user.click(switchTo3d);

    const switchTo2d = screen.getByRole('button', { name: 'Switch to 2D' });
    expect(switchTo2d).toHaveAttribute('aria-pressed', 'true');
    expect(switchTo2d).toHaveTextContent('3D');
    await waitFor(() => {
      expect(animation).toHaveBeenLastCalledWith(
        expect.anything(),
        expect.objectContaining({ y: 16, autoAlpha: 0 }),
        expect.objectContaining({ y: 0, autoAlpha: 1, ease: 'power3.out' }),
      );
    });

    animation.mockRestore();
  });
});
