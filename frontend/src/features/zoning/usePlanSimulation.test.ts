import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { FeatureCollection } from 'geojson';
import type { Plan, Scenario } from './types';
import { simulationDefaults } from './simulationTypes';
import { usePlanSimulation } from './usePlanSimulation';

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

it('opens saved server output without submitting another simulation', async () => {
  const plan={id:'plan',revision:2} as Plan;
  const scenario={id:'scenario'} as Scenario;
  const job={id:'saved-job',study_id:'study',status:'succeeded',result_id:'saved-result'};
  const fetch=vi.fn(async (url:string)=>new Response(JSON.stringify(url.endsWith('/simulation/latest')?{job}:url.includes('/runs/')?{id:'saved-result',options:[]}:job)));
  vi.stubGlobal('fetch',fetch);
  const {result,unmount}=renderHook(()=>usePlanSimulation(plan,scenario,simulationDefaults,'123'));
  await act(()=>result.current.loadSaved());
  expect(result.current.result?.id).toBe('saved-result');
  expect(fetch.mock.calls.some(([url])=>url.endsWith('/simulation/runs'))).toBe(false);
  unmount();
});

it('submits once and keeps a running job visible when more map tiles arrive', async () => {
  const plan = { id: 'plan', revision: 2 } as Plan;
  const scenario = { id: 'scenario' } as Scenario;
  const job = { id: 'job', study_id: 'study', status: 'queued', result_id: null };
  const fetch = vi.fn(async (_url: string, init?: RequestInit) => new Response(JSON.stringify(
    init?.method === 'POST' ? { study: { id: 'study' }, job } : job), { status: init?.method === 'POST' ? 202 : 200 }));
  vi.stubGlobal('fetch', fetch);
  const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
  const { result, rerender, unmount } = renderHook(({ buildings }) =>
    usePlanSimulation(plan, scenario, simulationDefaults, '123', true, buildings), { initialProps: { buildings: empty } });
  await act(() => result.current.run('screening'));
  await waitFor(() => expect(result.current.running).toBe(true));
  rerender({ buildings: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {},
    geometry: { type: 'Polygon', coordinates: [[[106.76,10.82],[106.761,10.82],[106.761,10.821],[106.76,10.82]]] } }] } });
  expect(result.current.job?.id).toBe('job');
  await act(() => result.current.run('screening'));
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  expect(fetch.mock.calls[0][0]).toContain('/zoning/plans/plan/simulation/runs');
  unmount();
});
