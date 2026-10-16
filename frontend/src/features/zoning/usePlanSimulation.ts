import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../../services/api';
import { ZoningRequestError, zoningRequest } from './api';
import type { Plan, Scenario } from './types';
import type { SimulationJob, SimulationResult, SimulationSettings, SimulationStudy } from './simulationTypes';
import type { FeatureCollection } from 'geojson';

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1/planning${path}`, {
    method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Simulation request failed (${response.status})`);
  return data;
}
const active = (job?: SimulationJob | null) => !!job && ['queued', 'running'].includes(job.status);

export function usePlanSimulation(plan: Plan, scenario: Scenario, settings: SimulationSettings, parcelId: string | null, enabled = true, mapBuildings?: FeatureCollection) {
  // Tiles keep streaming while a job runs. Its input is frozen on submission;
  // passive map updates must not hide the running job or invalidate its result.
  const key = JSON.stringify([plan.id, plan.revision, scenario.id, parcelId, enabled, settings]);
  const storageKey = `plan-simulation:${plan.id}:${scenario.id}:${parcelId ?? 'scenario'}`;
  const currentKey = useRef<string | null>(key);
  const [state, setState] = useState<{ key: string; study?: SimulationStudy; job?: SimulationJob; result?: SimulationResult }>();
  const [requesting, setRequesting] = useState(false), [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const submission = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => {
    currentKey.current = key;
    return () => { currentKey.current = null; };
  }, [key]);
  const visible = state?.key === key ? state : undefined;
  const remember = (job: SimulationJob) => {
    try { localStorage.setItem(storageKey, JSON.stringify({ key, id: job.id })); } catch { /* Storage may be unavailable. */ }
  };
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let id = visible?.job?.id;
    if (!id) try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (saved?.key === key && typeof saved.id === 'string') id = saved.id;
    } catch { /* Ignore an invalid local pointer; server inputs remain immutable. */ }
    if (!id) return;
    const poll = async () => {
      try {
        const job = await request<SimulationJob>(`/jobs/${encodeURIComponent(id!)}`, undefined, controller.signal);
        const result = job.status === 'succeeded' && job.result_id
          ? await request<SimulationResult>(`/runs/${job.result_id}`, undefined, controller.signal) : undefined;
        if (controller.signal.aborted || currentKey.current !== key) return;
        setState(previous => ({ ...(previous?.key === key ? previous : {}), key, job, result }));
        setError('');
        if (active(job)) timer = setTimeout(poll, 1500);
      } catch (reason) {
        if (!controller.signal.aborted && currentKey.current === key) {
          setError(reason instanceof Error ? reason.message : 'Unable to read simulation');
          // A failed poll does not mean a server job has stopped.
          timer = setTimeout(poll, 5000);
        }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [key, storageKey, visible?.job?.id, refresh, enabled]);

  const run = async (mode: 'screening' | 'native') => {
    if (!enabled || requesting || active(visible?.job)) return;
    setRequesting(true); setError('');
    try {
      const submissionKey = `${key}/${mode}`;
      if (submission.current?.key !== submissionKey) submission.current = { key: submissionKey, id: crypto.randomUUID() };
      const canonicalInput = {
        revision: plan.revision, scenario_id: scenario.id, parcel_id: parcelId, ...settings,
        mode, idempotency_key: submission.current.id,
      };
      const input = mapBuildings ? { ...canonicalInput, map_buildings: mapBuildings } : canonicalInput;
      let response: { study: SimulationStudy; job: SimulationJob };
      try {
        response = await zoningRequest(`/${plan.id}/simulation/runs`, input);
      } catch (cause) {
        if (!mapBuildings || !(cause instanceof ZoningRequestError) || cause.status !== 422) throw cause;
        // A provider tile is optional evidence, not a prerequisite for a saved run.
        response = await zoningRequest(`/${plan.id}/simulation/runs`, canonicalInput);
      }
      const { study, job } = response;
      remember(job);
      submission.current = null;
      if (currentKey.current === key) setState({ key, study, job });
    } catch (reason) {
      if (currentKey.current === key) setError(reason instanceof Error ? reason.message : 'Simulation unavailable');
    } finally { setRequesting(false); }
  };
  const action = async (operation: 'cancel' | 'retry') => {
    if (!visible?.job || requesting) return;
    setRequesting(true); setError('');
    try {
      const job = await request<SimulationJob>(`/jobs/${visible.job.id}/${operation}`, {});
      remember(job);
      if (currentKey.current === key) { setState({ key, study: visible.study, job }); setRefresh(value => value + 1); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Simulation unavailable'); }
    finally { setRequesting(false); }
  };
  const loadSaved = async () => {
    if (!enabled || requesting || active(visible?.job)) return;
    setRequesting(true); setError('');
    try {
      const saved=await zoningRequest<{job:SimulationJob | null}>(`/${plan.id}/simulation/latest`,{
        revision:plan.revision,scenario_id:scenario.id,parcel_id:parcelId,...settings,
      });
      if (!saved.job?.result_id) throw new Error('No completed run for this plan revision and scope.');
      const result=await request<SimulationResult>(`/runs/${saved.job.result_id}`);
      if (currentKey.current === key) {remember(saved.job);setState({key,job:saved.job,result});}
    } catch (reason) {if(currentKey.current === key) setError(reason instanceof Error ? reason.message : 'Saved result unavailable');}
    finally {setRequesting(false);}
  };
  return { ...visible, error: enabled ? error : '', requesting, running: active(visible?.job), run, action, loadSaved };
}
