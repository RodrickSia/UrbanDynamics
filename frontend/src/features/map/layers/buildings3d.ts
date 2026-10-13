import type { Map as MapLibreMap } from 'maplibre-gl';

/** The backend streams parcel-based models into this dataset layer. */
export const BUILDINGS_LAYER_ID = 'dataset-synthetic-buildings';

/** Basemap extrusions must stay hidden in both map modes and after a style swap. */
export function hideBasemapBuildingExtrusions(map: MapLibreMap): void {
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type === 'fill-extrusion' && layer.id !== BUILDINGS_LAYER_ID
      && !layer.id.startsWith('development-') && layer.layout?.visibility !== 'none') {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }
}
