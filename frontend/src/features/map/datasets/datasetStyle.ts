import type { LayerSpecification } from 'maplibre-gl';
import { type DataSelection, type DataLayerId, RISK_COLORS } from './datasets';
export const dataSourceId = (id: DataLayerId) => `dataset-${id}`;
export function datasetStyle(selection: DataSelection): LayerSpecification {
  const source = dataSourceId(selection.id);
  const common = { id: source, source, 'source-layer': 'features' };
  switch (selection.dataset) {
    case 'population':
      return {
        id: source,
        source,
        type: 'raster',
        // MapLibre's generic resampling is preferred; zero fade avoids tile cross-fade artifacts.
        // https://maplibre.org/maplibre-style-spec/layers/#raster-fade-duration
        paint: {
          'raster-opacity': 0.8,
          'raster-fade-duration': 0,
          resampling: 'linear',
        },
      };
    case 'flood_history':
      return {
        ...common,
        type: 'circle',
        paint: {
          'circle-radius': 5,
          'circle-color': '#2877dc',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1,
          'circle-opacity': 0.8,
        },
      };
    case 'flood_satellite':
      return {
        ...common,
        type: 'fill',
        paint: { 'fill-color': '#267bcc', 'fill-opacity': 0.45, 'fill-outline-color': '#175493' },
      };
    case 'flood_risk':
      return {
        ...common,
        type: 'fill',
        paint: {
          'fill-color': [
            'match',
            ['get', 'status'],
            'rain_alert_near_historical_flood',
            RISK_COLORS.alert,
            'no_rain_threshold_exceedance',
            RISK_COLORS.below,
            RISK_COLORS.unknown,
          ],
          'fill-opacity': 0.4,
          'fill-outline-color': '#576871',
        },
      };
    case 'land_price':
      return {
        ...common,
        type: 'line',
        minzoom: 8,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        filter: [
          'any',
          ['==', ['get', 'geometry_reviewed'], true],
          [
            'all',
            ['==', ['get', 'publication_match_mode'], 'automatic'],
            ['==', ['get', 'geometry_coverage'], 'whole_named_road_proxy'],
          ],
        ],
        paint: {
          'line-color': '#f59e0b',
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1, 13, 3, 17, 6],
          'line-opacity': 0.8,
        },
      };
    case 'parcels':
      return {
        ...common,
        type: 'fill',
        minzoom: 16,
        paint: {
          'fill-color': '#3da8ae',
          'fill-opacity': 0.18,
          'fill-outline-color': '#005b65',
        },
      };
  }
}
