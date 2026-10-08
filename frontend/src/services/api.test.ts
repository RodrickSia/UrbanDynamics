import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  API_BASE_URL,
  getLayerCatalog,
  getPopulationCatalog,
  getFeatures,
  tileUrl,
  dateQuery,
  ApiError,
} from './api';

afterEach(() => vi.unstubAllGlobals());
describe('published dataset API boundary', () => {
  it('uses actual loaded years, not an invented range', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ available: true, years: [{ year: 2022 }, { year: 2024 }] }),
          ),
        ),
    );
    expect((await getPopulationCatalog()).years).toEqual([2022, 2024]);
  });
  it('rejects malformed catalogs and does not display backend error bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('{"layers":{}}'))
        .mockResolvedValueOnce(new Response('private stack trace', { status: 503 })),
    );
    await expect(getLayerCatalog()).rejects.toThrow('Invalid API response');
    await expect(getLayerCatalog()).rejects.toEqual(new ApiError(503));
  });
  it('filters features by bounded WGS84 extent and an exclusive end date', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response('{"type":"FeatureCollection","features":[],"metadata":{"returned":0}}'),
      );
    vi.stubGlobal('fetch', fetcher);
    await getFeatures('flood_history', [106, 10, 107, 11], dateQuery('2024-01-01', '2024-02-01'));
    const url = new URL(fetcher.mock.calls[0][0], 'http://localhost');
    expect(url.searchParams.get('bbox')).toBe('106,10,107,11');
    expect(url.searchParams.get('end')).toBe('2024-02-01T00:00:00Z');
    expect(url.searchParams.get('limit')).toBe('1');
  });
  it('never applies time filters to land prices and keeps XYZ placeholders intact', () => {
    expect(tileUrl('land_price', { start: '2024-01-01' })).toBe(
      `${API_BASE_URL}/api/v1/layers/land_price/tiles/{z}/{x}/{y}.pbf`,
    );
    expect(tileUrl('population', {}, 2024, 'fire')).toContain(
      '/2024/tiles/{z}/{x}/{y}.png?palette=fire',
    );
    expect(tileUrl('population')).toContain('render=2');
    expect(tileUrl('flood_history')).toContain('schema=2');
    expect(() => dateQuery('2025-01-01', '2024-01-01')).toThrow('Start must be before end');
  });
});
