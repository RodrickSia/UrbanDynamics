import { expect, it, vi } from 'vitest';
import type { Map as MapLibreMap, LayerSpecification } from 'maplibre-gl';
import { createPoiVisibility, isPoiLayer } from '../layers/poi';

it('targets only POI symbols, not street labels, shields or custom markers', () => {
  const layer = (id: string, sourceLayer = '') =>
    ({
      id,
      type: 'symbol',
      source: 'map',
      'source-layer': sourceLayer,
    }) as LayerSpecification;
  expect(isPoiLayer(layer('poi-level-1'))).toBe(true);
  expect(isPoiLayer(layer('shops', 'poi'))).toBe(true);
  for (const id of ['road-label', 'road-shield', 'place-city', 'urban-measurement', 'waypoint'])
    expect(isPoiLayer(layer(id))).toBe(false);
});

it('restores original visibility and reapplies off to a newly loaded style', () => {
  let layers = [
    { id: 'poi-1', type: 'symbol', source: 'map' },
    {
      id: 'poi-hidden',
      type: 'symbol',
      source: 'map',
      layout: { visibility: 'none' },
    },
    { id: 'road-label', type: 'symbol', source: 'map' },
  ] as LayerSpecification[];
  const setLayoutProperty = vi.fn((id, _property, value) => {
    const l = layers.find((l) => l.id === id)!;
    l.layout = { ...l.layout, visibility: value };
  });
  const map = {
    getStyle: () => ({ layers }),
    setLayoutProperty,
  } as unknown as MapLibreMap;
  const apply = createPoiVisibility();
  apply(map, false);
  apply(map, false);
  expect(setLayoutProperty).toHaveBeenCalledTimes(1);
  apply(map, true);
  expect(layers[0].layout?.visibility).toBe('visible');
  expect(layers[1].layout?.visibility).toBe('none');
  layers = [{ id: 'poi-new', type: 'symbol', source: 'map' }];
  apply(map, false, true);
  expect(layers[0].layout?.visibility).toBe('none');
  apply(map, true);
  expect(layers[0].layout?.visibility).toBe('visible');
});
