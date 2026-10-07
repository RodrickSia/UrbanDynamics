import type { DataSelection } from './datasets';

export function viewportProbeDelayAfterMove(dataset: DataSelection['dataset']) {
  return dataset === 'population' ? 750 : 300;
}

export function populationRasterSource(url: string) {
  return {
    type: 'raster' as const,
    tiles: [url],
    tileSize: 256,
    // WorldPop's nominal ~100 m cells gain no new detail from z18 tile generation.
    // MapLibre reuses maxzoom tiles when viewing at higher zooms.
    // https://maplibre.org/maplibre-style-spec/sources/#maxzoom
    maxzoom: 17,
    bounds: [102, 8, 110, 24] as [number, number, number, number],
    attribution: 'WorldPop · persons per source raster cell',
  };
}
