import { describe, expect, it, vi } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { installMetricRoadWidths, metricRoadWidth } from '../layers/metricRoadWidths';

describe('metric road widths without decorative surfaces', () => {
  it('scales continuously in metres past the provider zoom-18 width cap', () => {
    const expression = metricRoadWidth(7, 10.8, { base: 1.2, stops: [[12, 0.2], [14, 0.5], [16, 6.92], [18, 18]] });
    const pixels16 = Number(expression[expression.length - 3]);
    const pixels24 = Number(expression.at(-1));
    for (const zoom of [16, 18.8, 19.1, 20.05, 22, 24]) {
      const fraction = (2 ** (zoom - 16) - 1) / (2 ** 8 - 1);
      const pixels = pixels16 + fraction * (pixels24 - pixels16);
      const metresPerPixel = 2 * Math.PI * 6371008.8 * Math.cos(10.8 * Math.PI / 180) / (512 * 2 ** zoom);
      expect(pixels * metresPerPixel).toBeCloseTo(7, 8);
    }
    expect(expression).not.toContain('get'); // camera-only: no terrain tile-LOD width jumps
    expect(metricRoadWidth(7, 22, 4).at(-1)).toBeGreaterThan(pixels24);
  });

  it('only edits widths/gaps of vehicle roads and cleans up its latitude listener', () => {
    const layers = [
      { id: 'road-street', type: 'line', source: 'composite', 'source-layer': 'streets', paint: { 'line-width': 18, 'line-color': '#ccddee' } },
      { id: 'bridge-primary-case', type: 'line', source: 'composite', 'source-layer': 'streets', paint: { 'line-width': 2, 'line-gap-width': 32 } },
      ...['road-path', 'road-major-tracks', 'aeroway-runway', 'tunnel-street'].map(id => ({ id, type: 'line', source: 'composite', 'source-layer': 'streets', paint: { 'line-width': 2 } })),
    ];
    const original = structuredClone(layers);
    let latitude = 10.8;
    const map = { getStyle: () => ({ layers }), getLayer: () => ({}),
      getCenter: () => ({ lat: latitude }), setPaintProperty: vi.fn(), on: vi.fn(), off: vi.fn(),
    } as unknown as MapLibreMap;
    const dispose = installMetricRoadWidths(map);
    expect(map.setPaintProperty).toHaveBeenCalledTimes(2);
    expect(map.setPaintProperty).toHaveBeenCalledWith('road-street', 'line-width', expect.any(Array));
    expect(map.setPaintProperty).toHaveBeenCalledWith('bridge-primary-case', 'line-gap-width', expect.any(Array));
    const update = vi.mocked(map.on).mock.calls[0][1] as () => void;
    update();
    expect(map.setPaintProperty).toHaveBeenCalledTimes(2);
    latitude = 22;
    update();
    expect(map.setPaintProperty).toHaveBeenCalledTimes(4);
    expect(layers).toEqual(original);
    dispose();
    expect(map.off).toHaveBeenCalledWith('moveend', update);
  });
});
