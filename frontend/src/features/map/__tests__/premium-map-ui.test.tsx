import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../../../App';

describe('premium map workspace', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_GOONG_MAPTILES_KEY', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('shows recent searches and lets the user remove an item', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('searchbox', { name: 'Search places' }));

    const workspace = screen.getByRole('region', { name: 'Search workspace' });
    expect(within(workspace).getByRole('button', { name: 'Hanoi, Vietnam' })).toBeInTheDocument();
    expect(within(workspace).queryByText('Sample results')).not.toBeInTheDocument();

    await user.click(within(workspace).getByRole('button', { name: 'Remove Hanoi from history' }));

    expect(within(workspace).queryByRole('button', { name: 'Hanoi, Vietnam' })).not.toBeInTheDocument();
  });

  it('shows disconnected data layers without enabling them', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Open data layers' }));

    const layers = screen.getByRole('region', { name: 'Data layers' });
    expect(within(layers).getByRole('checkbox', { name: 'Population density' })).toBeDisabled();
    expect(within(layers).getByRole('checkbox', { name: 'Rain' })).toBeDisabled();
    expect(within(layers).getByRole('checkbox', { name: 'Flood risk' })).toBeDisabled();
    expect(within(layers).getByRole('checkbox', { name: 'Land price' })).toBeDisabled();
    expect(within(layers).queryByText('Urban intelligence')).not.toBeInTheDocument();
    expect(within(layers).queryByText(/Add compatible datasets/i)).not.toBeInTheDocument();
    expect(within(layers).queryByText(/Waiting for a backend/i)).not.toBeInTheDocument();
    expect(within(layers).queryByText('API pending')).not.toBeInTheDocument();
    expect(layers).toHaveClass('glass-panel');
  });

  it('opens the compact measurement toolbar without shifting the right controls', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Measurement tools' }));
    await user.click(await screen.findByRole('button', { name: 'Measure distance' }));

    expect(screen.getByRole('region', { name: 'Distance measurement' })).toBeInTheDocument();
    expect(screen.getByTestId('navigation-cluster')).toHaveAttribute('data-right-panel-open', 'false');
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled();
  });

  it('keeps place details concise and glass-styled', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('searchbox', { name: 'Search places' }));
    await user.click(screen.getByRole('button', { name: 'Hanoi, Vietnam' }));

    const details = screen.getByRole('complementary', { name: 'Place details' });
    expect(details).toHaveClass('glass-panel');
    expect(within(details).queryByText(/sample data/i)).not.toBeInTheDocument();
    expect(within(details).queryByText(/backend endpoints/i)).not.toBeInTheDocument();
  });

  it('offers compatible basemaps and keeps planning visibly unavailable', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Choose basemap' }));

    // Wait for the GSAP entrance to make the panel accessible, not an arbitrary frame.
    const picker = await screen.findByRole('region', { name: 'Basemap' });
    expect(within(picker).getByRole('button', { name: 'Default' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(picker).getByRole('button', { name: 'Satellite' })).toBeEnabled();
    expect(within(picker).getByRole('button', { name: 'Planning' })).toBeDisabled();
  });

  it('keeps the basemap picker mounted while the pointer travels from the icon to its options', () => {
    render(<App />);

    const trigger = screen.getByRole('button', { name: 'Choose basemap' });
    const hoverArea = trigger.closest('.basemap-module');
    expect(hoverArea).not.toBeNull();

    fireEvent.mouseEnter(hoverArea!);
    expect(document.querySelector('.basemap-picker')).toBeInTheDocument();

    const pointerBridge = document.querySelector('.basemap-pointer-bridge');
    expect(pointerBridge).not.toBeNull();
    fireEvent.mouseLeave(hoverArea!, { relatedTarget: pointerBridge });

    expect(document.querySelector('.basemap-picker')).toBeInTheDocument();
  });
});
