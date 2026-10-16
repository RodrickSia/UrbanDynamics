import { describe, expect, it } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { getMapConfiguration, getMapStyle } from '../config/mapConfig';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import { setLayerOpacity, setMapMode, toggleLayerState } from '../state/layerState';
import { TIME_RANGE_OPTIONS } from '../types/map';
import { createLocationMarkerElement } from '../utils/locationMarkers';
import {
  calculateMeasurementSummary,
  createMeasurementSegments,
  formatMeasurementDistance,
} from '../utils/measurement';
import { readBuildingHeight, resolveMeasurementPoint } from '../utils/measurementElevation';

describe('map domain', () => {
  it('lists priority urban layers before future integrations', () => {
    expect(URBAN_LAYERS.slice(0, 7).map((layer) => layer.id)).toEqual([
      'poi',
      'buildings-3d',
      'synthetic-buildings',
      'population',
      'public-facilities',
      'sumo-network',
      'traffic',
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
    expect(toggleLayerState({ 'buildings-3d': false }, URBAN_LAYERS.find(l=>l.id==='buildings-3d')!)).toEqual({
      'buildings-3d': true,
    });
    expect(toggleLayerState({}, URBAN_LAYERS.find(l=>l.id==='population')!)).toEqual({});
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

  it('calculates horizontal, vertical, and straight-line 3D distance', () => {
    const points = [
      {
        id: 'start', longitude: 0, latitude: 0, elevationMeters: 10,
        elevationAvailable: true, surface: 'terrain' as const,
      },
      {
        id: 'end', longitude: 0.000898315, latitude: 0, elevationMeters: 30,
        elevationAvailable: true, surface: 'building' as const,
      },
    ];

    const summary = calculateMeasurementSummary(points);

    expect(summary.segmentCount).toBe(1);
    expect(summary.lastSegment?.horizontalMeters).toBeCloseTo(100, 0);
    expect(summary.lastSegment?.verticalMeters).toBe(20);
    expect(summary.lastSegment?.spatialMeters).toBeCloseTo(Math.sqrt(10_400), 0);
    expect(summary.elevationAvailable).toBe(true);
  });

  it('builds a 3D right triangle but keeps 2D measurement flat', () => {
    const points = [
      {
        id: 'start', longitude: 106.7, latitude: 10.8, elevationMeters: 8,
        elevationAvailable: true, surface: 'terrain' as const,
      },
      {
        id: 'end', longitude: 106.701, latitude: 10.801, elevationMeters: 28,
        elevationAvailable: true, surface: 'building' as const,
      },
    ];

    expect(createMeasurementSegments(points, '3d', true).map((segment) => segment.kind)).toEqual([
      'distance',
      'horizontal',
      'vertical',
    ]);
    expect(createMeasurementSegments(points, '2d')).toEqual([
      expect.objectContaining({ kind: 'distance', startElevation: 0, endElevation: 0 }),
    ]);
  });

  it('flags unavailable elevation and formats map-scale distances', () => {
    const summary = calculateMeasurementSummary([
      {
        id: 'start', longitude: 106.7, latitude: 10.8, elevationMeters: 0,
        elevationAvailable: false, surface: 'ground' as const,
      },
      {
        id: 'end', longitude: 106.701, latitude: 10.801, elevationMeters: 0,
        elevationAvailable: false, surface: 'ground' as const,
      },
    ]);

    expect(summary.elevationAvailable).toBe(false);
    expect(formatMeasurementDistance(842.4)).toBe('842.40 m');
    expect(formatMeasurementDistance(1_420)).toBe('1.42 km');
  });

  it('uses only explicit building elevation data', () => {
    expect(readBuildingHeight({ height: '36.5' })).toBe(36.5);
    expect(readBuildingHeight({ levels: 8 })).toBeNull();
    expect(readBuildingHeight({ name: 'Building without height' })).toBeNull();
    expect(readBuildingHeight({ height: -4 })).toBeNull();
  });

  it('does not invent a roof position when no surface intersection is available', () => {
    const createMap = (terrainElevation: number | null) => ({
      queryTerrainElevation: () => terrainElevation,
      getLayer: () => ({}),
      queryRenderedFeatures: () => [{
        layer: { id: 'urban-buildings-3d' },
        properties: { height: 20 },
      }],
    }) as unknown as MapLibreMap;

    expect(resolveMeasurementPoint(createMap(8), 106.7, 10.8, '3d', [0, 0], 'roof')).toEqual(
      expect.objectContaining({
        elevationMeters: 8,
        elevationAvailable: false,
        surface: 'building',
      }),
    );
    expect(resolveMeasurementPoint(createMap(null), 106.7, 10.8, '3d', [0, 0], 'ground')).toEqual(
      expect.objectContaining({
        elevationMeters: 0,
        elevationAvailable: false,
        surface: 'building',
      }),
    );
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
