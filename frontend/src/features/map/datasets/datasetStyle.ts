import type { LayerSpecification } from 'maplibre-gl';
import { type DataSelection, type DataLayerId, RISK_COLORS } from './datasets';
import { parcelFill } from './parcelStyle';
export const dataSourceId = (id: DataLayerId) => `dataset-${id}`;
export function datasetStyle(selection: DataSelection): LayerSpecification {
  const source = dataSourceId(selection.id);
  const common = {
    id: source,
    source,
    ...(selection.dataset === 'sumo_simulation' ? {} : { 'source-layer': 'features' }),
  };
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
          ['==', ['get', 'match_confidence'], 'spatially_checked'],
          [
            'all',
            ['==', ['get', 'publication_match_mode'], 'automatic'],
            ['==', ['get', 'match_confidence'], 'automatic_reference'],
            ['>', ['to-number', ['get', 'residential_vnd_m2'], 0], 0],
          ],
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
    case 'traffic':
      return {
        ...common,
        type: 'line',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': [
            'match', ['get', 'predicted_los'],
            'A', '#168a58', 'B', '#71ad45', 'C', '#d2b83f',
            'D', '#e58b32', 'E', '#d9583c', 'F', '#8c3047', '#8a9199',
          ],
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1, 13, 2.5, 17, 5],
          'line-opacity': 0.85,
        },
      };
    case 'sumo_network':
      return {
        ...common,
        type: 'line',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#647987',
          'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.45, 12, 1.2, 17, 3],
          'line-opacity': 0.72,
        },
      };
    case 'sumo_simulation':
      return {
        ...common,
        type: 'line',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': [
            'match', ['get', 'simulated_los'],
            'A', '#168a58', 'B', '#71ad45', 'C', '#d2b83f',
            'D', '#e58b32', 'E', '#d9583c', 'F', '#8c3047', '#8a9199',
          ],
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.1, 13, 2.7, 17, 5],
          'line-opacity': 0.9,
        },
      };
    case 'parcels':
      return parcelFill();
    case 'synthetic_buildings':
      return {
        ...common,
        type: 'fill-extrusion',
        minzoom: 14,
        paint: {
          'fill-extrusion-color': '#879b91',
          'fill-extrusion-height': ['to-number', ['get', 'height_m'], 3],
          'fill-extrusion-base': 0,
          'fill-extrusion-opacity': 0.82,
          'fill-extrusion-vertical-gradient': true,
        },
      };
  }
}
