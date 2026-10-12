import { describe, expect, it, vi } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { BUILDINGS_LAYER_ID, BUILDINGS_SOURCE_ID, setBuildings3d } from '../layers/buildings3d';

describe('GBA building layer', () => {
  it('hides Goong extrusions and uses the warehouse model at its recorded height', () => {
    const layers = new Map<string, unknown>();
    const sources = new Map<string, unknown>();
    const map = {
      getStyle: () => ({ layers: [
        { id: 'goong-buildings', type: 'fill-extrusion', source: 'composite', 'source-layer': 'VN_Building' },
        { id: 'street-labels', type: 'symbol', layout: { 'text-field': ['get', 'name'] } },
      ] }),
      getLayer: (id: string) => layers.get(id),
      getSource: (id: string) => sources.get(id),
      addLayer: vi.fn((layer: { id: string }) => layers.set(layer.id, layer)),
      removeLayer: vi.fn((id: string) => layers.delete(id)),
      addSource: vi.fn((id: string, source: unknown) => sources.set(id, source)),
      removeSource: vi.fn((id: string) => sources.delete(id)),
      setLayoutProperty: vi.fn(),
      setPaintProperty: vi.fn(),
      moveLayer: vi.fn(),
    };

    expect(setBuildings3d(map as unknown as MapLibreMap, true)).toBe(true);
    expect(map.setLayoutProperty).toHaveBeenCalledWith('goong-buildings', 'visibility', 'none');
    expect(map.addSource).toHaveBeenCalledWith(BUILDINGS_SOURCE_ID, expect.objectContaining({
      type: 'vector', maxzoom: 16,
      tiles: [expect.stringContaining('/api/v1/buildings/tiles/{z}/{x}/{y}.pbf')],
    }));
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({
      id: BUILDINGS_LAYER_ID, source: BUILDINGS_SOURCE_ID, 'source-layer': 'buildings',
      paint: expect.objectContaining({ 'fill-extrusion-height': ['to-number', ['get', 'height_m'], 0] }),
    }), 'street-labels');

    expect(setBuildings3d(map as unknown as MapLibreMap, false)).toBe(true);
    expect(map.removeLayer).toHaveBeenCalledWith(BUILDINGS_LAYER_ID);
    expect(map.removeSource).toHaveBeenCalledWith(BUILDINGS_SOURCE_ID);
  });
});
