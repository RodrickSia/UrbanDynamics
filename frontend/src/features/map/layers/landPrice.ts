import type { Map as MapLibreMap, MapLayerMouseEvent, VectorTileSource } from 'maplibre-gl';
import { API_BASE_URL } from '../../../services/api';

export const LAND_PRICE_SOURCE = 'urban-land-price';
export const LAND_PRICE_LAYER = 'urban-land-price-lines';
export const PRICE_COLORS = ['#2563eb', '#14b8a6', '#f59e0b', '#dc2626'] as const;
export interface LandPriceStatus {
  state: 'loading' | 'ready' | 'error';
  matched?: number;
  sourceRows?: number;
  pending?: number;
  regionCounts?: Record<string, number>;
  message?: string;
}
export type LandPriceProperties = Record<string, unknown>;

export function priceText(value: unknown): string {
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? `${new Intl.NumberFormat('vi-VN').format(amount)} ₫/m²` : 'Unavailable';
}

export function matchLabel(properties: LandPriceProperties): string {
  if (properties.geometry_reviewed === true && properties.source_values_reviewed === true) return 'Manually reviewed';
  if (properties.match_confidence === 'spatially_checked') return 'Spatial match · not manually reviewed';
  return 'Name-only match · geometry needs review';
}

export function installLandPrice(
  map: MapLibreMap, opacity: number,
  onStatus: (status: LandPriceStatus) => void,
  onSelect: (properties: LandPriceProperties | null) => void,
) {
  const abort = new AbortController();
  let disposed = false;
  let loading = false;
  let version = '';
  onStatus({ state: 'loading' });
  const click = (event: MapLayerMouseEvent) => {
    const properties = event.features?.[0]?.properties;
    if (properties) onSelect(properties);
  };
  const error = (event: unknown) => {
    if (typeof event === 'object' && event !== null && 'sourceId' in event && event.sourceId === LAND_PRICE_SOURCE && !disposed) {
      onStatus({ state: 'error', message: 'Land-price tiles could not be loaded. Please retry.' });
    }
  };
  async function load() {
    if (disposed || loading) return;
    loading = true;
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/layers/land_price/tilejson.json`,
        { signal: abort.signal, cache: 'no-cache' });
      if (!response.ok) throw new Error('Price layer unavailable');
      const body = await response.json() as { metadata?: Record<string, unknown> };
      if (disposed) return;
      const metadata = body.metadata ?? {};
      const nextVersion = String(metadata.updated_at ?? metadata.ingested_at ?? 'unknown');
      // Our same-origin template preserves the public port behind Nginx.
      // Versioned vector tiles load only visible areas and refresh after ETL.
      const base = new URL(API_BASE_URL || '/', window.location.origin).href.replace(/\/$/, '');
      const tiles = [`${base}/api/v1/layers/land_price/tiles/{z}/{x}/{y}.pbf?v=${encodeURIComponent(nextVersion)}`];
      const existing = map.getSource(LAND_PRICE_SOURCE) as VectorTileSource | undefined;
      if (existing) {
        if (version !== nextVersion) {
          existing.setTiles(tiles);
          onSelect(null);
        }
      } else {
        map.addSource(LAND_PRICE_SOURCE, {
          type: 'vector', tiles, minzoom: 8, maxzoom: 18,
          attribution: '© OpenStreetMap contributors · Official reference prices',
        });
        map.addLayer({
          id: LAND_PRICE_LAYER, source: LAND_PRICE_SOURCE, 'source-layer': 'features', type: 'line', minzoom: 8,
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': ['interpolate', ['linear'], ['to-number', ['get', 'residential_vnd_m2'], 0],
              0, PRICE_COLORS[0], 20_000_000, PRICE_COLORS[1], 100_000_000, PRICE_COLORS[2], 300_000_000, PRICE_COLORS[3]],
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.5, 13, 4, 18, 8],
            'line-opacity': opacity,
          },
        });
        map.on('click', LAND_PRICE_LAYER, click);
        map.on('error', error);
      }
      version = nextVersion;
      onStatus({ state: 'ready', matched: Number(metadata.matched_rows ?? 0),
        sourceRows: Number(metadata.source_rows ?? 0), pending: Number(metadata.pending_rows ?? 0),
        regionCounts: metadata.matched_region_counts as Record<string, number> | undefined });
    } catch {
      if (!disposed) onStatus({ state: 'error', message: 'Land-price data is unavailable. Please retry.' });
    } finally {
      loading = false;
    }
  }
  void load();
  const timer = window.setInterval(() => { void load(); }, 300_000);
  return () => {
    disposed = true;
    abort.abort();
    window.clearInterval(timer);
    map.off('click', LAND_PRICE_LAYER, click);
    map.off('error', error);
    if (map.getLayer(LAND_PRICE_LAYER)) map.removeLayer(LAND_PRICE_LAYER);
    if (map.getSource(LAND_PRICE_SOURCE)) map.removeSource(LAND_PRICE_SOURCE);
  };
}
