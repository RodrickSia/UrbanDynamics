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
const sumoSelection: DataSelection = {
  id: 'sumo-simulation',
  dataset: 'sumo_simulation',
  url: '/api/v1/traffic/sumo-simulations/runs/test/features',
  year: 2026,
  dates: {},
  sumoRunId: 'test',
  sumoVolumeMax: 120,
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

  it('colors every SUMO road by the run-specific estimated car volume scale', () => {
    const style = datasetStyle(sumoSelection);
    const color = (style.paint as Record<string, unknown> | undefined)?.['line-color'];

    expect(color).toEqual([
      'interpolate', ['linear'], ['to-number', ['get', 'estimated_cars_6h'], 0],
      0, '#277da1', 30, '#50b5b0', 60, '#b8d76b', 90, '#f2ae49', 120, '#c43d3d',
    ]);
  });
});
