import type { Map as MapLibreMap } from 'maplibre-gl';

/** The backend streams parcel-based models into this dataset layer. */
export const BUILDINGS_LAYER_ID = 'dataset-synthetic-buildings';

/** Keep Goong's own building extrusion visible alongside streamed models. */
export function showGoongBuildingExtrusions(map: MapLibreMap): void {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === 'fill-extrusion' &&
      (layer.source === 'composite' || layer['source-layer'] === 'VN_Building') &&
      layer.layout?.visibility === 'none') {
      map.setLayoutProperty(layer.id, 'visibility', 'visible');
    }
  }
}
