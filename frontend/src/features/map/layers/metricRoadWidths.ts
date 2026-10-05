import type { ExpressionSpecification, Map as MapLibreMap } from 'maplibre-gl';

// Display estimates per carriageway, not surveyed road boundaries.
const WIDTH_METRES: Record<string, number> = {
  motorway: 22, trunk: 18, primary: 14, secondary: 10, tertiary: 8,
  street: 7, service: 4, link: 6, 'trunk-link': 7, 'motorway-link': 7,
};
const EARTH_CIRCUMFERENCE = 2 * Math.PI * 6371008.8; // MapLibre's mean Earth radius

/** Camera-only width avoids feature/zoom interpolation varying by terrain tile LOD. */
export function metricRoadWidth(metres: number, latitude: number, original: unknown): ExpressionSpecification {
  const pixels = (zoom: number) => metres * 512 * 2 ** zoom
    / (EARTH_CIRCUMFERENCE * Math.cos(Math.max(-85, Math.min(85, latitude)) * Math.PI / 180));
  const stops = original && typeof original === 'object' && 'stops' in original && Array.isArray(original.stops)
    ? original.stops.filter((stop): stop is [number, number] => Array.isArray(stop)
      && typeof stop[0] === 'number' && typeof stop[1] === 'number' && stop[0] < 16)
    : [[0, typeof original === 'number' ? original : 1], [15, typeof original === 'number' ? original : 1]];
  // Keep overview stop values; from street zoom onward 2^zoom gives a constant
  // geographic width, including fractional zooms and overzoom past source z17.
  return ['interpolate', ['exponential', 2], ['zoom'], ...stops.flat(), 16, pixels(16), 24, pixels(24)];
}

export function installMetricRoadWidths(map: MapLibreMap): () => void {
  const widths: { id: string; property: 'line-width' | 'line-gap-width'; metres: number; original: unknown }[] = [];
  for (const layer of map.getStyle().layers ?? []) {
    if (layer.type !== 'line' || layer.source !== 'composite' || layer['source-layer'] !== 'streets') continue;
    // Only Goong's vehicle carriageways. Leave rail, pedestrian, tunnel and
    // runway styles alone, including their patterned or dashed paint.
    const match = /^(?:road|bridge)-(motorway-link|trunk-link|motorway|trunk|primary|secondary|tertiary|street|service|link)(-case)?(?:-200)?$/.exec(layer.id);
    if (!match) continue;
    const gap = layer.paint?.['line-gap-width'];
    const property = match[2] && gap != null ? 'line-gap-width' : 'line-width';
    widths.push({ id: layer.id, property, metres: WIDTH_METRES[match[1]] + (match[2] && gap == null ? 1 : 0),
      original: layer.paint?.[property] });
  }
  let latitude = NaN;
  const update = () => {
    const next = map.getCenter().lat;
    if (Math.abs(next - latitude) < 0.05) return;
    latitude = next;
    for (const width of widths) if (map.getLayer(width.id)) {
      map.setPaintProperty(width.id, width.property, metricRoadWidth(width.metres, latitude, width.original));
    }
  };
  update();
  map.on('moveend', update);
  return () => { map.off('moveend', update); };
}
