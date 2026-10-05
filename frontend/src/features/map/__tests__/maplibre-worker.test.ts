import { describe, expect, it, vi } from 'vitest';

import { configureMapLibreWorker } from '../config/maplibreWorker';

describe('MapLibre worker configuration', () => {
  it('sets an explicit Vite-managed worker URL before map initialization', () => {
    const setWorkerUrl = vi.fn();

    configureMapLibreWorker({ setWorkerUrl });

    expect(setWorkerUrl).toHaveBeenCalledOnce();
    expect(setWorkerUrl).toHaveBeenCalledWith(expect.stringContaining('maplibre-gl-worker'));
  });
});
