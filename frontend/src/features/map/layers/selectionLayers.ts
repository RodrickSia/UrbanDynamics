import type { Feature, FeatureCollection, Geometry, LineString, Point, Position } from 'geojson';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import type { MapSelection } from '../types/map';

const SOURCE_ID = 'urban-selection';

export function ensureSelectionLayers(map: MapLibreMap): void {
  if (!map.getSource(SOURCE_ID)) {
    map.addSource(SOURCE_ID, { type: 'geojson', data: emptyCollection() });
  }
  if (!map.getLayer('urban-selection-fill')) {
    map.addLayer({
      id: 'urban-selection-fill',
      type: 'fill',
      source: SOURCE_ID,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#0d766e', 'fill-opacity': 0.18 },
    });
  }
  if (!map.getLayer('urban-selection-line')) {
    map.addLayer({
      id: 'urban-selection-line',
      type: 'line',
      source: SOURCE_ID,
      paint: { 'line-color': '#0a5e58', 'line-width': 2.5, 'line-dasharray': [2, 1.5] },
    });
  }
  if (!map.getLayer('urban-selection-points')) {
    map.addLayer({
      id: 'urban-selection-points',
      type: 'circle',
      source: SOURCE_ID,
      filter: ['==', ['geometry-type'], 'Point'],
      paint: {
        'circle-radius': 4,
        'circle-color': '#f7fbf8',
        'circle-stroke-color': '#0a5e58',
        'circle-stroke-width': 2,
      },
    });
  }
}

export function updateSelectionLayers(
  map: MapLibreMap,
  draftCoordinates: Position[],
  selection: MapSelection,
): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) return;
  const features: Array<Feature<Geometry>> = [];

  if (selection?.kind === 'polygon') features.push(selection.geometry);
  if (draftCoordinates.length > 1) {
    features.push({
      type: 'Feature',
      properties: { draft: true },
      geometry: { type: 'LineString', coordinates: draftCoordinates } satisfies LineString,
    });
  }
  draftCoordinates.forEach((coordinate, index) => {
    features.push({
      type: 'Feature',
      properties: { draft: true, index },
      geometry: { type: 'Point', coordinates: coordinate } satisfies Point,
    });
  });
  source.setData({ type: 'FeatureCollection', features });
}

function emptyCollection(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}
