import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useBackendLayers } from '../datasets/useBackendLayers';
import type { LayerState } from '../types/map';

afterEach(() => vi.unstubAllGlobals());
function fixture(options: { populationFails?: boolean; land?: boolean; reviewed?: boolean } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const path = new URL(input, 'http://localhost').pathname;
      if (path.endsWith('/population'))
        return new Response(
          JSON.stringify({ available: true, years: [{ year: 2022 }, { year: 2030 }] }),
          { status: options.populationFails ? 503 : 200 },
        );
      if (path.endsWith('/land_price/features'))
        return new Response(
          JSON.stringify({
            type: 'FeatureCollection',
            features: options.land ? [{ properties: { geometry_reviewed: options.reviewed } }] : [],
            metadata: {},
          }),
        );
      return new Response(
        JSON.stringify({
          layers: [
            { id: 'flood_history', available: true },
            { id: 'land_price', available: true },
            { id: 'flood_risk', available: true, stale: true },
            { id: 'flood_satellite', available: false },
          ],
        }),
      );
    }),
  );
}
describe('backend layer availability and selections', () => {
  it('keeps catalog availability separate from user opt-in and defaults to an existing nonfuture year', async () => {
    fixture();
    const { result, rerender } = renderHook(({ layers }) => useBackendLayers(layers), {
      initialProps: { layers: {} as LayerState },
    });
    await waitFor(() => expect(result.current.catalog.population?.available).toBe(true));
    expect(result.current.year).toBe(2022);
    expect(result.current.selections).toEqual([]);
    rerender({ layers: { population: true, 'flood-history': true } });
    expect(result.current.selections.map((s) => s.dataset)).toEqual([
      'population',
      'flood_history',
    ]);
    act(() => result.current.setYear(2030));
    expect(result.current.selections[0].url).toContain('/2030/tiles/');
  });
  it('keeps empty or unreviewed prices unavailable while flood and POI still work', async () => {
    fixture({ populationFails: true, land: true, reviewed: false });
    const { result } = renderHook(() =>
      useBackendLayers({ 'land-price': true, 'flood-history': true }),
    );
    await waitFor(() => expect(result.current.catalog['land-price']?.status).toBe('ready'));
    expect(result.current.catalog['land-price']?.available).toBe(false);
    expect(result.current.catalog.population?.status).toBe('error');
    expect(result.current.definitions.find((l) => l.id === 'poi')?.status).toBe('available');
    expect(result.current.selections.map((s) => s.dataset)).toEqual(['flood_history']);
  });
  it('recovers a failed catalog and keeps date filtering off reviewed prices', async () => {
    fixture({ populationFails: true, land: true, reviewed: true });
    const { result } = renderHook(() =>
      useBackendLayers({ population: true, flood: true, 'land-price': true }),
    );
    await waitFor(() => expect(result.current.catalog.population?.status).toBe('error'));
    fixture({ land: true, reviewed: true });
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.catalog.population?.available).toBe(true));
    act(() => result.current.setDates({ start: '2024-01-01T00:00:00Z' }));
    expect(result.current.selections.find((s) => s.dataset === 'flood_risk')?.url).toContain(
      'start=',
    );
    expect(result.current.selections.find((s) => s.dataset === 'land_price')?.url).not.toContain(
      'start=',
    );
    expect(result.current.catalog.flood?.stale).toBe(true);
  });
});
