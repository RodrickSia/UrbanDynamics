import type { StyleSpecification } from 'maplibre-gl';

export const DEFAULT_VIEWPORT = {
  center: [107.8, 16.1] as [number, number],
  zoom: 4.7,
  pitch: 0,
  bearing: 0,
} as const;

export const MAP_STYLES = [
  { id: 'standard', label: 'Default', asset: 'goong_map_web.json' },
  { id: 'satellite', label: 'Satellite', asset: 'goong_satellite.json' },
] as const;

export type MapStyleId = (typeof MAP_STYLES)[number]['id'];

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
