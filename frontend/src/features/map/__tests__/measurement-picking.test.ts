import { describe, expect, it, vi } from 'vitest';
import { MercatorCoordinate, type Map as MapLibreMap, type MapGeoJSONFeature } from 'maplibre-gl';
import { MeasurementProjection } from '../utils/measurementProjection';
import { resolveMeasurementPoint } from '../utils/measurementElevation';
import { prepareSnapGeometry, snapCandidates, type SnapGeometry } from '../utils/measurementSnap';
import { pickBuildingSurface } from '../utils/measurementPicking';
import { createMapInteractionHandlers } from '../utils/mapInteractions';
import type { UrbanMapProps } from '../components/UrbanMap.types';

const ring = [[106.7, 10.8], [106.701, 10.8], [106.701, 10.801], [106.7, 10.801], [106.7, 10.8]];
const building = (id: string, height = 20) => ({
  id, source: 'buildings', sourceLayer: 'footprints', properties: { height },
  geometry: { type: 'Polygon', coordinates: [ring] },
}) as unknown as MapGeoJSONFeature;
const mapFor = (features: MapGeoJSONFeature[], elevation = 8) => ({
  queryTerrainElevation: () => elevation, getLayer: () => ({}),
  queryRenderedFeatures: () => features,
  getCanvas: () => ({ clientWidth: 1000, clientHeight: 700 }),
}) as unknown as MapLibreMap;
const camera = () => {
  const projection = new MeasurementProjection(MercatorCoordinate);
  const m = MercatorCoordinate.fromLngLat([106.7002, 10.8002]);
  vi.spyOn(projection, 'ray').mockReturnValue({ near: [m.x, m.y, 0.001], far: [m.x, m.y, 0] });
  return projection;
};

describe('world raycast and geometry snapping', () => {
  it('retries a surface whose ground elevation was unavailable when first cached', () => {
    const feature = building('delayed-dem');
    const map = mapFor([feature]); const projection = camera();
    map.queryTerrainElevation = () => null;
    expect(pickBuildingSurface(map, feature, [300,200], projection, 20)?.groundElevation).toBeNull();
    map.queryTerrainElevation = () => 8;
    const hit = pickBuildingSurface(map, feature, [300,200], projection, 20);
    expect(hit?.groundElevation).toBe(8);
    expect(hit?.elevation).toBeCloseTo(28, 3);
  });
  it('refreshes visible candidates after the final terrain/tile render becomes idle', () => {
    const map = mapFor([]); const projection = camera();
    expect(resolveMeasurementPoint(map,106.7002,10.8002,'3d',[300,200],undefined,projection)?.surface).not.toBe('building');
    map.queryRenderedFeatures = (() => [building('newly-rendered')]) as MapLibreMap['queryRenderedFeatures'];
    const handlers = createMapInteractionHandlers(map, () => ({ mode: '3d',
      measurement: { status: 'active', points: [], preview: null },
    } as unknown as UrbanMapProps), projection);
    handlers.idle();
    expect(resolveMeasurementPoint(map,106.7002,10.8002,'3d',[300,200],undefined,projection))
      .toMatchObject({ surface: 'building', elevationAvailable: true });
  });
  it('keeps settled geometry cached across overlay-only idle frames', () => {
    const map = mapFor([building('settled')]); const projection = camera();
    const query = vi.spyOn(map,'queryRenderedFeatures');
    const handlers = createMapInteractionHandlers(map, () => ({ mode:'3d',
      measurement:{ status:'active', points:[], preview:null },
    } as unknown as UrbanMapProps), projection);
    handlers.idle();
    const pick = () => resolveMeasurementPoint(map,106.7002,10.8002,'3d',[300,200],undefined,projection);
    pick(); handlers.idle(); pick(); handlers.idle(); pick();
    expect(query).toHaveBeenCalledTimes(1);
    handlers.scenechange(); handlers.idle(); pick();
    expect(query).toHaveBeenCalledTimes(2);
  });
  it('chooses the nearest building independently of feature order', () => {
    for (const features of [[building('low'), building('high', 40)], [building('high', 40), building('low')]]) {
      const point = resolveMeasurementPoint(mapFor(features),106.7002,10.8002,'3d',[300,200],undefined,camera());
      expect(point?.elevationMeters).toBeCloseTo(48, 3);
      expect(point?.snap).toMatchObject({ kind: 'face', objectId: 'buildings:footprints:high', primitiveId: '0:roof' });
    }
  });
  it('lets nearer terrain occlude a building hit', () => {
    const map = mapFor([building('behind-terrain')]);
    map.unproject = () => ({ lng: 106.7002, lat: 10.8002 }) as ReturnType<MapLibreMap['unproject']>;
    map.queryTerrainElevation = (ll) => {
      const latitude = Array.isArray(ll) ? ll[1] : 'lat' in ll ? ll.lat : 0;
      return Math.abs(latitude - 10.8005) < 0.00001 ? 8 : 80;
    };
    expect(resolveMeasurementPoint(map,106.7002,10.8002,'3d',[300,200],undefined,camera()))
      .toMatchObject({ surface: 'terrain', elevationMeters: 80, snap: { kind: 'ground' } });
  });
  it('does not turn courtyard holes into roof surfaces', () => {
    const feature = building('courtyard');
    if (feature.geometry.type !== 'Polygon') throw new Error('Invalid fixture');
    feature.geometry.coordinates.push([[106.7001,10.8001],[106.7003,10.8001],
      [106.7003,10.8003],[106.7001,10.8003],[106.7001,10.8001]]);
    expect(pickBuildingSurface(mapFor([feature]),feature,[300,200],camera(),20)).toBeNull();
  });
  it('stores incident edges on vertices and refuses unknown ground geometry', () => {
    const feature = building('one'); const projection = camera();
    const geometry = prepareSnapGeometry(mapFor([feature]), feature, projection, 20);
    expect(geometry.edges).toHaveLength(12);
    expect(geometry.vertices).toHaveLength(8);
    expect(geometry.vertices.every(vertex => vertex.edges.length === 3)).toBe(true);
    const changedDEM = prepareSnapGeometry(mapFor([feature], 9), feature, projection, 20);
    expect(changedDEM.edges.map(edge => edge.metadata.id)).toEqual(geometry.edges.map(edge => edge.metadata.id));
    const map = mapFor([feature]); map.queryTerrainElevation = () => null;
    expect(prepareSnapGeometry(map,feature,projection,20).edges).toHaveLength(0);
  });
  it('uses perspective-correct world interpolation when snapping a sloped edge', () => {
    const projection = new MeasurementProjection(MercatorCoordinate);
    projection.matrix = [1,0,0,0, 0,1,0,0, 0,0,1,1, 0,0,0,0];
    vi.spyOn(projection, 'project').mockImplementation(([x,y,z]) => ({ x: x / z * 100, y: y / z * 100, visible: true }));
    const geometry: SnapGeometry = { objectId: 'slope', vertices: [], edges: [{
      a: [0,0,1], b: [2,0,2], metadata: { id: 'edge', objectId: 'slope', start: [0,0,1], end: [2,0,2] },
    }] };
    const [snap] = snapCandidates(geometry,[50,0],projection,1000,700);
    expect(snap.position[0]).toBeCloseTo(2 / 3);
    expect(snap.position[2]).toBeCloseTo(4 / 3);
    expect(projection.project(snap.position,1000,700)?.x).toBeCloseTo(50);
  });
});
