import type { ExpressionSpecification, FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';

export const PARCEL_MIN_ZOOM = 12;
export const PARCEL_MAX_NATIVE_ZOOM = 16;
export const PARCEL_OUTLINE = 'dataset-parcels-outline';
const color: ExpressionSpecification = ['to-color', ['get', 'color'], '#94a3b8'];

export function parcelFill(): FillLayerSpecification {
  return {
    id: 'dataset-parcels', source: 'dataset-parcels', 'source-layer': 'features',
    type: 'fill', minzoom: PARCEL_MIN_ZOOM,
    paint: { 'fill-color': color, 'fill-opacity': 0.44, 'fill-antialias': false },
  };
}

export function parcelOutline(): LineLayerSpecification {
  return {
    id: PARCEL_OUTLINE, source: 'dataset-parcels', 'source-layer': 'features',
    type: 'line', minzoom: PARCEL_MIN_ZOOM,
    paint: {
      'line-color': '#35545a',
      'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.25, 14, 0.65, 16, 1.35, 19, 2],
      'line-opacity': 0.85,
    },
  };
}
