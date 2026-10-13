import { describe, expect, it, vi } from 'vitest';
import { MercatorCoordinate, type Map as MapLibreMap } from 'maplibre-gl';
import { MeasurementProjection, localProjectionMatrix } from '../utils/measurementProjection';

import {
  buildMeasurementLineVertices,
  FLOATS_PER_LINE_VERTEX,
  MEASUREMENT_COLORS,
  MEASUREMENT_SURFACE_OFFSET_METERS,
} from '../layers/measurementLayer';
import { BUILDINGS_LAYER_ID, showGoongBuildingExtrusions } from '../layers/buildings3d';
import { setTerrain, TERRAIN_TILEJSON_URL } from '../layers/terrain';
import {
  refreshMeasurementPointElevation,
  resolveMeasurementPoint,
  readBuildingHeight,
} from '../utils/measurementElevation';
import { createMeasurementSegments } from '../utils/measurement';
import { readTerrainElevation } from '../utils/terrainElevation';

describe('3D measurement regressions', () => {
  it('does not recreate active terrain when unrelated scene settings change', () => {
    const map = {
      getTerrain: () => ({ source: 'urban-terrain-dem', exaggeration: 1 }),
      getSource: () => ({}), getLayer: () => ({}), setTerrain: vi.fn(),
    } as unknown as MapLibreMap;
    setTerrain(map, true);
    setTerrain(map, true);
    expect(map.setTerrain).not.toHaveBeenCalled();
  });
  it('keeps local acquired DEM data usable while distant terrain tiles load', () => {
    const map = { getTerrain: () => ({source:'dem'}), isSourceLoaded: () => false,
      queryTerrainElevation: () => 12 } as unknown as MapLibreMap;
    expect(readTerrainElevation(map, [106.7,10.8])).toBe(12);
  });
  it('reads Goong max_height instead of inventing a 12m building', () => {
    expect(readBuildingHeight({ max_height: 68, min_height: 12 })).toBe(68);
  });
  it('treats zero building height as unavailable, without masking a valid alternate height', () => {
    expect(readBuildingHeight({ max_height: 0 })).toBeNull();
    expect(readBuildingHeight({ max_height: '0', height: 18 })).toBe(18);
    expect(readBuildingHeight({ max_height: -2, render_height: 24 })).toBe(24);
  });
  it('shows Goong extrusions without changing the streamed model layer', () => {
    const setLayoutProperty = vi.fn();
    const map = {
      setLayoutProperty,
      getStyle: () => ({ layers: [
        { id: 'building', type: 'fill-extrusion', source: 'composite', 'source-layer': 'VN_Building', layout: { visibility: 'none' } },
        { id: BUILDINGS_LAYER_ID, type: 'fill-extrusion', source: BUILDINGS_LAYER_ID },
      ] }),
    } as unknown as MapLibreMap;
    showGoongBuildingExtrusions(map);
    expect(setLayoutProperty).toHaveBeenCalledWith('building', 'visibility', 'visible');
    expect(setLayoutProperty).not.toHaveBeenCalledWith(BUILDINGS_LAYER_ID, 'visibility', expect.anything());
  });
  it('does not mistake the unloaded DEM zero for acquired sea-level elevation', () => {
    const map = {
      getTerrain: () => ({ source: 'urban-terrain-dem' }),
      isSourceLoaded: () => false,
      queryTerrainElevation: () => 0,
    } as unknown as MapLibreMap;
    expect(readTerrainElevation(map, [106.7, 10.8])).toBeNull();
  });
  it('anchors a building measurement to the clicked roof surface, not the footprint center', () => {
    const map = {
      queryTerrainElevation: () => 8,
      getLayer: () => ({}),
      getCanvas: () => ({ clientWidth: 1000, clientHeight: 700 }),
      queryRenderedFeatures: () => [{
        layer: { id: BUILDINGS_LAYER_ID },
        properties: { height: 20 },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [106.7, 10.8],
            [106.701, 10.8],
            [106.701, 10.801],
            [106.7, 10.801],
            [106.7, 10.8],
          ]],
        },
      }],
    } as unknown as MapLibreMap;

    const projection = new MeasurementProjection(MercatorCoordinate);
    const m = MercatorCoordinate.fromLngLat([106.7008, 10.8002]);
    vi.spyOn(projection, 'ray').mockReturnValue({ near: [m.x, m.y, 0.001], far: [m.x, m.y, 0] });
    const point = resolveMeasurementPoint(map, 106.73, 10.83, '3d', [240, 180], 'building', projection)!;

    expect(point.longitude).toBeCloseTo(106.7008, 7);
    expect(point.latitude).toBeCloseTo(10.8002, 7);
    expect(point.elevationMeters).toBeCloseTo(28, 3);
    expect(point.surface).toBe('building');
  });

  it('does not move or downgrade a fixed building point while terrain tiles reload', () => {
    const fixedPoint = {
      id: 'fixed-building',
      longitude: 106.7005,
      latitude: 10.8005,
      elevationMeters: 28,
      elevationAvailable: true,
      surface: 'building' as const,
      buildingHeightMeters: 20,
    };
    const map = {
      queryTerrainElevation: () => null,
    } as unknown as MapLibreMap;

    expect(refreshMeasurementPointElevation(map, fixedPoint)).toEqual(fixedPoint);
  });

  it('freezes acquired elevation when DEM level of detail changes on zoom', () => {
    const fixedPoint = {
      id: 'fixed-building',
      longitude: 106.7005,
      latitude: 10.8005,
      elevationMeters: 28,
      elevationAvailable: true,
      surface: 'building' as const,
      buildingHeightMeters: 20,
    };
    const map = {
      queryTerrainElevation: () => 9,
    } as unknown as MapLibreMap;

    expect(refreshMeasurementPointElevation(map, fixedPoint)).toEqual(fixedPoint);
  });

  it('uses a yellow overlay without displacing it from the picked surface', () => {
    expect(MEASUREMENT_COLORS.horizontal).toEqual([0.98, 0.68, 0.12, 1]);
    expect(MEASUREMENT_SURFACE_OFFSET_METERS).toBe(0);
  });

  it('does not duplicate a level distance with a horizontal component', () => {
    const points = [
      {
        id: 'start', longitude: 106.7, latitude: 10.8, elevationMeters: 12,
        elevationAvailable: true, surface: 'terrain' as const,
      },
      {
        id: 'end', longitude: 106.701, latitude: 10.801, elevationMeters: 12,
        elevationAvailable: true, surface: 'terrain' as const,
      },
    ];

    expect(createMeasurementSegments(points, '3d').map((segment) => segment.kind)).toEqual([
      'distance',
    ]);
  });

  it('builds every measurement edge as a camera-stable thick triangle strip', () => {
    const projected = {
      fromLngLat: ([longitude, latitude]: [number, number], elevation: number) => ({
        x: longitude,
        y: latitude,
        z: elevation,
      }),
    };
    const segments = [{
      kind: 'horizontal' as const,
      start: [106.7, 10.8] as [number, number],
      end: [106.701, 10.801] as [number, number],
      startElevation: 12,
      endElevation: 12,
    }];

    const vertices = buildMeasurementLineVertices(
      projected as never,
      segments,
    );

    expect(vertices).toHaveLength(6 * FLOATS_PER_LINE_VERTEX);
    expect(Array.from(vertices).every(Number.isFinite)).toBe(true);
  });

  it('configures terrain from the documented global DEM TileJSON source', () => {
    const addSource = vi.fn();
    const map = {
      getSource: () => undefined,
      addSource,
      getLayer: () => undefined,
      addLayer: vi.fn(),
      getStyle: () => ({ layers: [] }),
      setTerrain: vi.fn(),
    } as unknown as MapLibreMap;

    setTerrain(map, true);

    expect(TERRAIN_TILEJSON_URL).toBe('https://tiles.mapterhorn.com/tilejson.json');
    expect(addSource).toHaveBeenCalledWith('urban-terrain-dem', {
      type: 'raster-dem',
      url: TERRAIN_TILEJSON_URL,
      encoding: 'terrarium',
      tileSize: 512,
      maxzoom: 12,
    });
    expect(map.setTerrain).toHaveBeenCalledWith({
      source: 'urban-terrain-dem',
      exaggeration: 1,
    });
  });

  it('preserves centimetre-scale positions when sent to a float32 GPU', () => {
    const origin = MercatorCoordinate.fromLngLat([106.7, 10.8]);
    const matrix = [1e9, 0, 0, 0, 0, 1e9, 0, 0, 0, 0, 1, 0, -origin.x * 1e9, -origin.y * 1e9, 0, 1];
    const local = localProjectionMatrix(matrix, [origin.x, origin.y, 0]);
    expect(local[12]).toBe(0);
    expect(local[13]).toBe(0);
    const vertices = buildMeasurementLineVertices(MercatorCoordinate, [{
      kind: 'distance', start: [106.7, 10.8], end: [106.7000001, 10.8000001], startElevation: 0, endElevation: 0,
    }], [origin.x, origin.y, 0]);
    expect(vertices[0]).toBe(0);
    expect(vertices[1]).toBe(0);
    expect(vertices[3]).not.toBe(0);
    const expected = MercatorCoordinate.fromLngLat([106.7000001, 10.8000001]);
    expect(Math.abs(vertices[3] - (expected.x - origin.x)) / origin.meterInMercatorCoordinateUnits()).toBeLessThan(0.001);
  });

  it('does not add another building layer when the basemap lacks one', () => {
    const addLayer = vi.fn();
    const map = {
      addLayer, setLayoutProperty: vi.fn(),
      getStyle: () => ({
        layers: [
          { id: 'urban-terrain-hillshade', type: 'hillshade' },
          { id: BUILDINGS_LAYER_ID, type: 'fill-extrusion', source: BUILDINGS_LAYER_ID },
          { id: 'place-labels', type: 'symbol', layout: { 'text-field': ['get', 'name'] } },
        ],
      }),
    } as unknown as MapLibreMap;

    showGoongBuildingExtrusions(map);
    expect(addLayer).not.toHaveBeenCalled();
  });
});
