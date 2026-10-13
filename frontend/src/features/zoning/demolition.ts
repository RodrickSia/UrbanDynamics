import type { FilterSpecification, Map as MapLibreMap } from 'maplibre-gl';
import { convertFilter, type ExpressionFilterSpecification } from '@maplibre/maplibre-gl-style-spec';
import type { PolygonGeometry } from './types';
import { polygonsIntersect } from './developmentGeometry';

/** Restore provider filters on cleanup; never mutate source assets. */
export function installDemolition(map: MapLibreMap, masks: PolygonGeometry[]) {
  const originals = new Map<string, FilterSpecification | null>();
  const applied = new Map<string, string>();
  const update = () => {
    if (!map.isStyleLoaded()) return;
    for (const layer of map.getStyle().layers) {
      if (layer.type !== 'fill-extrusion' || layer.id.startsWith('development-')) continue;
      if (!originals.has(layer.id)) originals.set(layer.id, map.getFilter(layer.id) ?? null);
      const ids = new Set<string | number>();
      const features = map.querySourceFeatures(layer.source, { sourceLayer: layer['source-layer'] });
      for (const f of features) {
        if (f.id === undefined || (f.geometry.type !== 'Polygon' && f.geometry.type !== 'MultiPolygon')) continue;
        if (masks.some(mask => polygonsIntersect(f.geometry as PolygonGeometry, mask))) ids.add(f.id);
      }
      const clauses: ExpressionFilterSpecification[] = [];
      const original = originals.get(layer.id);
      if (original) clauses.push(convertFilter(original));
      // A fully-contained footprint can also be hidden without a provider feature ID.
      for (const mask of masks) clauses.push(['!', ['within', mask]]);
      if (ids.size) clauses.push(['!', ['in', ['id'], ['literal', [...ids]]]]);
      const filter: FilterSpecification = ['all', ...clauses];
      const key = JSON.stringify(filter);
      if (applied.get(layer.id) !== key) { map.setFilter(layer.id, filter); applied.set(layer.id, key); }
    }
  };
  const style = () => { originals.clear(); applied.clear(); update(); };
  update(); map.on('idle', update); map.on('style.load', style);
  return () => {
    map.off('idle', update); map.off('style.load', style);
    for (const [id, filter] of originals) if (map.getLayer(id)) map.setFilter(id, filter);
  };
}
