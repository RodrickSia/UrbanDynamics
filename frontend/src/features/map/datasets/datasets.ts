import type { Dataset, Palette, DateQuery } from '../../../services/api';
import type { UrbanLayerId } from '../types/map';

export const DATASETS = {
  population: 'population',
  flood: 'flood_risk',
  'flood-history': 'flood_history',
  'flood-satellite': 'flood_satellite',
  'land-price': 'land_price',
} as const satisfies Partial<Record<UrbanLayerId, Dataset>>;
export type DataLayerId = keyof typeof DATASETS;
export const DATA_LAYER_IDS = Object.keys(DATASETS) as DataLayerId[];
export function isDataLayer(id: UrbanLayerId): id is DataLayerId {
  return id in DATASETS;
}
export type DataStatus = 'loading' | 'ready' | 'empty' | 'error';
export interface LayerReport {
  status: DataStatus;
  message: string;
}
export interface DataSelection {
  id: DataLayerId;
  dataset: Dataset;
  url: string;
  year: number;
  dates: DateQuery;
}
// Keep synchronized with backend/app/services/raster_tiles.py; values are people/cell.
export const PALETTE_STOPS: Record<Palette, ReadonlyArray<readonly [number, string]>> = {
  pseudocolor: [
    [1, '#ffffb2'],
    [10, '#fecc5c'],
    [50, '#fd8d3c'],
    [100, '#f03b20'],
    [500, '#bd0026'],
    [1000, '#800026'],
  ],
  greyscale: [
    [1, '#f5f5f5'],
    [10, '#d2d2d2'],
    [100, '#787878'],
    [1000, '#141414'],
  ],
  fire: [
    [1, '#fff5b4'],
    [10, '#ffb446'],
    [50, '#eb4623'],
    [100, '#910018'],
    [1000, '#2d000a'],
  ],
};
export const RISK_COLORS = { alert: '#df6824', below: '#189b91', unknown: '#8a9199' };
