import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { installLandPrice, LAND_PRICE_LAYER, LAND_PRICE_SOURCE } from '../layers/landPrice';
import { LandPriceLegend } from '../components/LandPriceLegend';
import { matchLabel } from '../layers/landPrice';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import { toggleLayerState } from '../state/layerState';

afterEach(() => vi.unstubAllGlobals());

function fakeMap() {
  let source: unknown;
  let layer: unknown;
  const map = {
    addSource: vi.fn((_id, value) => { source = value; }),
    addLayer: vi.fn(value => { layer = value; }),
    getSource: vi.fn(() => source), getLayer: vi.fn(() => layer),
    removeLayer: vi.fn(() => { layer = undefined; }),
    removeSource: vi.fn(() => { source = undefined; }), on: vi.fn(), off: vi.fn(),
  };
  return map;
}

describe('land-price map connection', () => {
  it('enables the actual layer without claiming time-series support', () => {
    const layer = URBAN_LAYERS.find(l => l.id === 'land-price')!;
    expect(toggleLayerState({},layer)['land-price']).toBe(true);
    expect(layer.supportsTimeRange).toBe(false);
  });

  it('uses visible-area vector tiles and ignores reverse-proxy URLs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async () => ({
      tiles:['http://wrong-host/api/tile.pbf'],metadata:{matched_rows:42,source_rows:9502,pending_rows:9460},
    })}));
    const map = fakeMap(); const status = vi.fn();
    const dispose = installLandPrice(map as unknown as MapLibreMap,.65,status,vi.fn());
    await vi.waitFor(() => expect(status).toHaveBeenLastCalledWith(expect.objectContaining({state:'ready',matched:42})));
    expect(map.addSource).toHaveBeenCalledWith(LAND_PRICE_SOURCE,expect.objectContaining({
      type:'vector',tiles:[expect.stringContaining('/api/v1/layers/land_price/tiles/{z}/{x}/{y}.pbf')],
    }));
    expect(map.addLayer.mock.calls[0][0].paint['line-opacity']).toBe(.65);
    dispose();
    expect(map.removeLayer).toHaveBeenCalledWith(LAND_PRICE_LAYER);
    expect(map.removeSource).toHaveBeenCalledWith(LAND_PRICE_SOURCE);
  });

  it('does not install a stale response after disabling the layer', async () => {
    let finish: (value: unknown) => void = () => undefined;
    vi.stubGlobal('fetch',vi.fn().mockImplementation(() => new Promise(resolve => {finish=resolve;})));
    const map = fakeMap();const dispose=installLandPrice(map as unknown as MapLibreMap,.8,vi.fn(),vi.fn());
    dispose();finish({ok:true,json:async () => ({metadata:{matched_rows:1}})});
    await Promise.resolve();await Promise.resolve();
    expect(map.addSource).not.toHaveBeenCalled();
  });

  it('reports a source outage instead of a successful empty layer', async () => {
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false}));
    const map=fakeMap();const status=vi.fn();const dispose=installLandPrice(map as unknown as MapLibreMap,.8,status,vi.fn());
    await vi.waitFor(() => expect(status).toHaveBeenLastCalledWith(expect.objectContaining({state:'error'})));
    expect(map.addLayer).not.toHaveBeenCalled();dispose();
  });

  it('shows prices, partial coverage and review status without rendering source HTML', () => {
    render(<LandPriceLegend status={{state:'ready',matched:42,sourceRows:9502,pending:9460}}
      selected={{road:'<img src=x onerror=alert(1)>',residential_vnd_m2:152900000,
        match_confidence:'spatially_checked',source_url:'javascript:alert(1)'}}
      onClose={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.getByText('152.900.000 ₫/m²')).toBeInTheDocument();
    expect(screen.getByText('Spatial match · not manually reviewed')).toBeInTheDocument();
    expect(screen.getByText(/Blank areas have no mapped price/)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
    expect(matchLabel({geometry_reviewed:true,source_values_reviewed:false})).not.toBe('Manually reviewed');
  });
});
