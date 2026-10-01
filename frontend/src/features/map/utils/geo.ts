import area from '@turf/area';
import bbox from '@turf/bbox';
import type { Feature, Polygon, Position } from 'geojson';

import type { PolygonSelection } from '../types/map';

export function createPolygonSelection(coordinates: Position[]): PolygonSelection {
  if (coordinates.length < 3) {
    throw new Error('At least three points are required to create a research area.');
  }

  const ring = [...coordinates, coordinates[0]];
  const geometry: Feature<Polygon> = {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Polygon', coordinates: [ring] },
  };
  const measuredBounds = bbox(geometry);

  return {
    kind: 'polygon',
    geometry,
    areaSquareMeters: area(geometry),
    vertexCount: coordinates.length,
    bounds: [measuredBounds[0], measuredBounds[1], measuredBounds[2], measuredBounds[3]],
  };
}
