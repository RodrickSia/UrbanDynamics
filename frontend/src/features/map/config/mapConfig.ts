import type { StyleSpecification } from 'maplibre-gl';

export const DEFAULT_VIEWPORT = {
  center: [106.75785, 10.82403] as [number, number],
  zoom: 13,
  pitch: 0,
  bearing: 0,
} as const;

export const MAP_STYLES = [
  { id: 'standard', label: 'Default', asset: 'goong_map_web.json' },
  { id: 'satellite', label: 'Satellite', asset: 'goong_satellite.json' },
] as const;

export type MapStyleId = (typeof MAP_STYLES)[number]['id'];

/** Visible-browser fallback; normal HTTP cache, no prefetch or offline download. */
export function getFallbackMapStyle():StyleSpecification {
  return {version:8,name:'OpenStreetMap fallback',
    glyphs:'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
    sources:{'osm-fallback':{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize:256,maxzoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'}},
    layers:[{id:'osm-fallback',type:'raster',source:'osm-fallback'}]};
}

export type MapConfiguration =
  | { ok: true; mapKey: string; styleUrl: string }
  | { ok: false; message: string };

export function getStyleUrl(mapKey: string, style: MapStyleId = 'standard'): string {
  const selectedStyle = MAP_STYLES.find((candidate) => candidate.id === style) ?? MAP_STYLES[0];
  return `https://tiles.goong.io/assets/${selectedStyle.asset}?api_key=${encodeURIComponent(mapKey)}`;
}

export function getMapStyle(
  mapKey: string,
  style: MapStyleId = 'standard',
): string | StyleSpecification {
  if (style !== 'satellite') return getStyleUrl(mapKey, style);

  return {
    version: 8,
    name: 'Goong satellite imagery',
    sources: {
      'satellite-imagery': {
        type: 'raster',
        tiles: [
          `https://satellite.goong.io/{z}/{x}/{y}.png?api_key=${encodeURIComponent(mapKey)}`,
        ],
        tileSize: 256,
        minzoom: 0,
        maxzoom: 20,
      },
    },
    layers: [
      {
        id: 'satellite-imagery',
        type: 'raster',
        source: 'satellite-imagery',
      },
    ],
  };
}

export function getMapConfiguration(mapKey: string | undefined): MapConfiguration {
  const normalizedKey = mapKey?.trim();

  if (!normalizedKey) {
    return {
      ok: false,
      message:
        'Goong Map Tiles Key is not configured. Set VITE_GOONG_MAPTILES_KEY in frontend/.env.local.',
    };
  }

  return { ok: true, mapKey: normalizedKey, styleUrl: getStyleUrl(normalizedKey) };
}
