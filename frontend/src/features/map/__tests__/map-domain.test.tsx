import { describe, expect, it } from 'vitest';

import { getMapConfiguration, getMapStyle } from '../config/mapConfig';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import { setLayerOpacity, setMapMode, toggleLayerState } from '../state/layerState';
import { TIME_RANGE_OPTIONS } from '../types/map';
import { createPolygonSelection } from '../utils/geo';
import { createLocationMarkerElement } from '../utils/locationMarkers';

describe('map domain', () => {
  it('lists priority urban layers before future integrations', () => {
    expect(URBAN_LAYERS.slice(0, 5).map((layer) => layer.id)).toEqual([
      'buildings-3d',
      'population',
      'public-facilities',
      'traffic',
      'flood',
    ]);
  });

  it('contains the eight required time ranges', () => {
    expect(TIME_RANGE_OPTIONS.map((option) => option.label)).toEqual([
      '30 minutes',
      '1 hour',
      '1 day',
      '1 week',
      '1 month',
      '3 months',
      '6 months',
      '1 year',
    ]);
  });

  it('returns a developer-friendly error when the map key is missing', () => {
    expect(getMapConfiguration('')).toEqual({
      ok: false,
      message:
        'Goong Map Tiles Key is not configured. Set VITE_GOONG_MAPTILES_KEY in frontend/.env.local.',
    });
  });

  it('uses a raster-only satellite style so labels are not rendered twice', () => {
    const style = getMapStyle('public-test-key', 'satellite');

    expect(style).not.toBeTypeOf('string');
    if (typeof style === 'string') return;
    expect(style.layers).toEqual([
      expect.objectContaining({ id: 'satellite-imagery', type: 'raster' }),
    ]);
    expect(style.layers.some((layer) => layer.type === 'symbol')).toBe(false);
  });

  it('toggles available layers without enabling disconnected data', () => {
    expect(toggleLayerState({ 'buildings-3d': false }, URBAN_LAYERS[0])).toEqual({
      'buildings-3d': true,
    });
    expect(toggleLayerState({}, URBAN_LAYERS[1])).toEqual({});
  });

  it('keeps the 2D/3D mode and building layer in sync', () => {
    expect(setMapMode({}, '3d')).toEqual({ mode: '3d', layers: { 'buildings-3d': true } });
    expect(setMapMode({ 'buildings-3d': true }, '2d')).toEqual({
      mode: '2d',
      layers: { 'buildings-3d': false },
    });
  });

  it('clamps future layer opacity to the supported range', () => {
    expect(setLayerOpacity({}, 'buildings-3d', 1.4)).toEqual({ 'buildings-3d': 1 });
    expect(setLayerOpacity({}, 'buildings-3d', -0.2)).toEqual({ 'buildings-3d': 0 });
  });

  it('closes a polygon and calculates its geometry metadata', () => {
    const selection = createPolygonSelection([
      [105.8, 21],
      [105.9, 21],
      [105.9, 21.1],
    ]);

    expect(selection.geometry.geometry.coordinates[0][0]).toEqual(
      selection.geometry.geometry.coordinates[0].at(-1),
    );
    expect(selection.vertexCount).toBe(3);
    expect(selection.areaSquareMeters).toBeGreaterThan(0);
    expect(selection.bounds).toEqual([105.8, 21, 105.9, 21.1]);
  });

  it('creates distinct accessible markers for user and selected locations', () => {
    const userMarker = createLocationMarkerElement('user');
    const selectedMarker = createLocationMarkerElement('selected');

    expect(userMarker).toHaveClass('location-marker--user');
    expect(userMarker).toHaveAttribute('aria-label', 'Your location');
    expect(selectedMarker).toHaveClass('location-marker--selected');
    expect(selectedMarker).toHaveAttribute('aria-label', 'Selected location');
  });
});
