import type { LayerSpecification, Map as MapLibreMap } from 'maplibre-gl';

/** POI symbols only: road shields, street/city names and user markers stay on. */
export function isPoiLayer(layer: LayerSpecification): boolean {
  return (
    layer.type === 'symbol' &&
    /(^|[-_\s])poi(s)?($|[-_\s])/i.test(`${layer.id} ${layer['source-layer'] ?? ''}`)
  );
}

/** Keep provider-hidden POIs hidden when switching our overlay back on. */
export function createPoiVisibility() {
  const original = new Map<string, 'visible' | 'none'>();
  return (map: MapLibreMap, enabled: boolean, newStyle = false) => {
    if (newStyle) original.clear();
    for (const layer of map.getStyle().layers ?? []) {
      if (!isPoiLayer(layer)) continue;
      const current = layer.layout?.visibility === 'none' ? 'none' : 'visible';
      if (!original.has(layer.id)) original.set(layer.id, current);
      const visibility = enabled ? original.get(layer.id)! : 'none';
      if (current !== visibility) map.setLayoutProperty(layer.id, 'visibility', visibility);
    }
  };
}
