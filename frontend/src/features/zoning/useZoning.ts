import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteZoningPlan, zoningRequest } from './api';
import { sketchGeometry } from './geometry';
import type { Command, Plan, PlanSummary, PolygonGeometry, Preview, Sketch, Tool } from './types';

const EMPTY_SKETCH: Sketch = { tool: null, points: [], geometry: null };

export function useZoning(parcelAvailable = false) {
  const [panel, setPanel] = useState<'plans' | 'indicators' | null>(null);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [typeId, setTypeId] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [sketch, setSketchState] = useState<Sketch>(EMPTY_SKETCH);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [policy, setPolicyState] = useState<'preserve' | 'replace'>('preserve');
  const [opacity, setOpacity] = useState(.35);
  const [visible, setVisible] = useState(true);
  const [showParcels, setShowParcels] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [focus, setFocus] = useState<{ key: number; geometry: PolygonGeometry } | null>(null);
  const pending = useRef(false);
  const scenario = plan?.scenarios.find(s => s.id === scenarioId) ?? plan?.scenarios[0] ?? null;
  const readOnly = !scenario || scenario.locked || scenario.kind === 'reference';
  const chosenType = plan?.types.find(t => t.id === typeId) ?? plan?.types[0];
  const active = panel !== null;
  const cancel = useCallback(() => { setSketchState(EMPTY_SKETCH); setPreview(null); }, []);
  const setSketch = useCallback((value: Sketch) => { setSketchState(value); setPreview(null); }, []);
  const setPolicy = (value: 'preserve' | 'replace') => { setPolicyState(value); setPreview(null); };
  const zoomTo = (geometry: PolygonGeometry) => setFocus(current => ({ key: (current?.key ?? 0) + 1, geometry }));

  const run = async <T,>(operation: () => Promise<T>): Promise<T | null> => {
    if (pending.current) return null;
    pending.current = true; setBusy(true); setError('');
    try { return await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to save plan'); return null; }
    finally { pending.current = false; setBusy(false); }
  };

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try { setPlans((await zoningRequest<{ plans: PlanSummary[] }>('', undefined, signal)).plans); setError(''); }
    catch (cause) { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'Unable to load plans'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [active, refresh]);

  const openPlan = async (id: string) => {
    const next = await run(() => zoningRequest<Plan>(`/${encodeURIComponent(id)}`));
    if (!next) return;
    setPlan(next); setScenarioId(next.scenarios.find(s => s.kind === 'proposal')?.id ?? next.scenarios[0].id);
    setSelected([]); cancel(); zoomTo(next.study_area);
  };
  const execute = async (action: string, payload: Record<string, unknown> = {}, target = scenario?.id ?? null) => {
    if (!plan) return null;
    const next = await run(() => zoningRequest<Plan>(`/${plan.id}/commands`, {
      revision: plan.revision, scenario_id: target, action, payload,
    }));
    if (next) {
      setPlan(next); cancel();
      setSelected(ids => ids.filter(id => next.scenarios.find(s => s.id === target)?.zones.some(z => z.id === id)));
      if (action === 'add_scenario') { setScenarioId(next.scenarios.at(-1)!.id); setSelected([]); }
      if (action === 'add_type' || action === 'duplicate_type') setTypeId(next.types.at(-1)!.id);
    }
    return next;
  };
  const create = async (name: string, description: string, horizon: number | null) => {
    const geometry = sketchGeometry(sketch);
    if (!geometry || geometry.type === 'LineString') { setError('Draw a study area with at least three points'); return; }
    const next = await run(() => zoningRequest<Plan>('', { name, description, horizon, study_area: geometry }));
    if (next) { setPlan(next); setScenarioId(next.scenarios[1].id); cancel(); zoomTo(next.study_area); void refresh(); }
  };
  const deletePlan = async (id: string, revision: number) => {
    const result = await run(() => deleteZoningPlan(id, revision).then(() => true));
    if (result) {
      if (plan?.id === id) { setPlan(null); setScenarioId(null); setSelected([]); cancel(); }
      setPlans(current => current.filter(item => item.id !== id));
    }
    return result;
  };
  const buildCommand = (): Command | null => {
    const geometry = sketchGeometry(sketch);
    if (!plan || !scenario || !geometry) { setError('Add enough points to complete the shape'); return null; }
    return { revision: plan.revision, scenario_id: scenario.id, action: sketch.tool ?? 'draw', payload: {
      geometry, ...(sketch.tool === 'split' ? { zone_id: selected[0] } : {
        type_id: chosenType?.id, policy, ...(sketch.tool === 'reshape' ? { zone_id: selected[0] } : {}),
      }),
    } };
  };
  const finish = async () => {
    if (sketch.tool === 'study' || sketch.tool === 'edit-study') return;
    const command = buildCommand();
    if (!command || !plan) return;
    if (sketch.tool === 'split') { await execute('split', command.payload); return; }
    const result = await run(() => zoningRequest<Preview>(`/${plan.id}/preview`, command));
    if (result) setPreview(result);
  };
  const confirm = async () => { const command = buildCommand(); if (command && preview) await execute(command.action, command.payload); };
  const begin = (tool: Tool) => {
    if (busy) return;
    const zone = scenario?.zones.find(z => z.id === selected[0]);
    if (tool === 'reshape' && zone) {
      setTypeId(zone.type_id); setSketch({ tool, geometry: structuredClone(zone.geometry), points: [] });
    } else if (tool === 'edit-study' && plan) {
      setSketch({ tool, geometry: structuredClone(plan.study_area), points: [] });
    } else setSketch({ tool, geometry: null, points: [] });
    setError('');
  };
  const selectScenario = (id: string) => {
    if (busy) return;
    setScenarioId(id); cancel();
    setSelected(ids => ids.filter(zoneId => plan?.scenarios.find(s => s.id === id)?.zones.some(z => z.id === zoneId)));
  };
  const pick = (id: string | null, multiple: boolean) => {
    if (busy) return;
    setSelected(ids => !id ? [] : multiple ? ids.includes(id) ? ids.filter(i => i !== id) : [...ids, id] : [id]);
  };
  const close = () => { if (!busy) { setPanel(null); cancel(); } };
  return { panel, setPanel, active, close, plan, plans, scenario, chosenType, typeId, setTypeId, selected, pick,
    sketch, setSketch, begin, cancel, preview, policy, setPolicy, finish, confirm, readOnly, opacity, setOpacity,
    visible, setVisible, showParcels, setShowParcels, parcelAvailable, busy, loading, error, setError, focus, zoomTo, openPlan, execute, create, deletePlan, refresh, selectScenario,
    back: () => { setPlan(null); setSelected([]); cancel(); void refresh(); },
  };
}
export type ZoningWorkspace = ReturnType<typeof useZoning>;
