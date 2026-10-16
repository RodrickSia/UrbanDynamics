import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import type { Plan, Scenario, Sketch } from './types';
import { useDevelopment } from './useDevelopment';

afterEach(() => vi.unstubAllGlobals());

it('keeps a zoning site selectable when optional map buildings fail validation', async () => {
  const zoneId = 'zone:00000000-0000-0000-0000-000000000001';
  const geometry = { type: 'Polygon' as const, coordinates: [[
    [106.76, 10.82], [106.761, 10.82], [106.761, 10.821], [106.76, 10.82],
  ]] };
  const plan = { id: 'plan', revision: 2, parcels: {} } as Plan;
  const scenario = { id: 'scenario' } as Scenario;
  const sketch: Sketch = { tool: null, geometry: null, points: [] };
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
    ? new Response(JSON.stringify({ detail: [{ loc: ['body', 'features', 0], msg: 'Invalid geometry' }] }), { status: 422 })
    : new Response(JSON.stringify({ parcel: { id: zoneId, geometry, source: 'scenario.zone', land_use: 'RES' } })));
  vi.stubGlobal('fetch', fetch);
  const { result } = renderHook(() => useDevelopment(plan, scenario, sketch, vi.fn(), vi.fn(), vi.fn()));
  act(() => result.current.pickParcel(zoneId));
  await waitFor(() => expect(result.current.parcel?.id).toBe(zoneId));
  const buildings: FeatureCollection = { type: 'FeatureCollection', features: [] };
  act(() => result.current.onBaseline(zoneId, buildings));
  await waitFor(() => expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1));
  await waitFor(() => expect(fetch.mock.calls.filter(([, init]) => init?.method !== 'POST')).toHaveLength(2));
  expect(result.current.error).toBeUndefined();
  expect(result.current.mapBuildings).toBeUndefined();
  expect(result.current.parcel?.id).toBe(zoneId);
});
