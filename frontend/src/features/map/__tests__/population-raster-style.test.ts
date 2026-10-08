import { describe, expect, it } from 'vitest';
import { datasetStyle } from '../datasets/datasetStyle';
import type { DataSelection } from '../datasets/datasets';
import { populationRasterSource, viewportProbeDelayAfterMove } from '../datasets/populationRaster';

const populationSelection: DataSelection = {
  id: 'population',
  dataset: 'population',
  url: '/api/v1/population/2030/tiles/{z}/{x}/{y}.png',
  year: 2030,
  dates: {},
};

describe('Population raster rendering', () => {
  it('keeps linear resampling and disables tile cross-fade seams', () => {
    const style = datasetStyle(populationSelection);

    expect(style.type).toBe('raster');
    expect(style.paint).toMatchObject({
      resampling: 'linear',
      'raster-fade-duration': 0,
    });
  });

  it('waits for the map to settle before probing population coverage after movement', () => {
    expect(viewportProbeDelayAfterMove('population')).toBe(750);
    expect(viewportProbeDelayAfterMove('flood_risk')).toBe(300);
  });

  it('reuses max-zoom tiles for overzoom instead of requesting redundant detail tiles', () => {
    expect(populationRasterSource(populationSelection.url)).toMatchObject({
      type: 'raster',
      tileSize: 256,
      maxzoom: 17,
      bounds: [102, 8, 110, 24],
    });
  });
});
