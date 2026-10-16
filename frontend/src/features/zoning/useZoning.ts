import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deleteZoningPlan, zoningRequest } from './api';
import { sketchGeometry } from './geometry';
import { useDevelopment } from './useDevelopment';
import type { IndicatorChart } from './indicatorChart';
import type { Command, Plan, PlanSummary, PolygonGeometry, Preview, Sketch, Tool } from './types';

const EMPTY_SKETCH: Sketch = { tool: null, points: [], geometry: null };

export function useZoning(parcelAvailable = false, assistantBusy = false) {
  const [panel, setPanel] = useState<'plans' | 'indicators' | null>(null);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [displayedPlans, setDisplayedPlans] = useState<Record<string, PolygonGeometry>>({});
  const [displayedPlanDetails, setDisplayedPlanDetails] = useState<Record<string, Plan>>({});
  const [lastDisplayedPlanId, setLastDisplayedPlanId] = useState<string | null>(null);
  const [loadingPlanId, setLoadingPlanId] = useState<string | null>(null);
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
  const [section, setSectionState] = useState<'info' | 'zoning' | 'development' | 'dashboard'>('zoning');
  const [analysisSelection, setAnalysisSelection] = useState<{ planId: string | null; geometry: PolygonGeometry } | null>(null);
  const [includeScenario, setIncludeScenario] = useState(true);
  const [indicatorChart, setIndicatorChart] = useState<IndicatorChart | null>(null);
  const [leaving, setLeaving] = useState(false);
  const leaveAction = useRef<(() => void) | null>(null);
  const pending = useRef(false);
  const removedPlanIds = useRef(new Set<string>());
  const scenario = plan?.scenarios.find(s => s.id === scenarioId) ?? plan?.scenarios[0] ?? null;
  const readOnly = !scenario || scenario.locked || scenario.kind === 'reference';
  const chosenType = plan?.types.find(t => t.id === typeId) ?? plan?.types[0];
  const displayedId = lastDisplayedPlanId && displayedPlans[lastDisplayedPlanId] ? lastDisplayedPlanId
    : Object.keys(displayedPlans).at(-1);
  const indicatorPlan = plan ?? (displayedId ? displayedPlanDetails[displayedId] : null) ?? null;
  let rememberedScenario: string | null = null;
  if (indicatorPlan && !plan) {
    try { rememberedScenario = localStorage.getItem(`urban-plan-scenario-${indicatorPlan.id}`); } catch { /* Optional preference. */ }
  }
  const indicatorScenario = indicatorPlan?.scenarios.find(s => s.id === (plan ? scenarioId : rememberedScenario ?? scenarioId))
    ?? indicatorPlan?.scenarios.find(s => s.kind === 'proposal') ?? indicatorPlan?.scenarios[0] ?? null;
  const displayedPlanScenes = useMemo(() => Object.entries(displayedPlanDetails).flatMap(([id, details]) => {
    if (!displayedPlans[id]) return [];
    let remembered: string | null = null;
    try { remembered = localStorage.getItem(`urban-plan-scenario-${id}`); } catch { /* Optional preference. */ }
    const displayedScenario = details.scenarios.find(s => s.id === (plan?.id === id ? scenarioId : remembered))
      ?? details.scenarios.find(s => s.kind === 'proposal') ?? details.scenarios[0];
    return displayedScenario ? [{ plan: details, scenario: displayedScenario }] : [];
  }), [displayedPlanDetails, displayedPlans, plan?.id, scenarioId]);
  const active = panel !== null;
  const analyzing = active && (panel === 'indicators' || (!!plan && section === 'dashboard'));
  const analysisArea = panel === 'plans' && section === 'dashboard' ? plan?.study_area ?? null
    : analysisSelection?.planId === (indicatorPlan?.id ?? null) ? analysisSelection.geometry : indicatorPlan?.study_area ?? null;
  const useStudyArea = () => { setAnalysisSelection(null); cancel(); };
  const indicatorScope = JSON.stringify([indicatorPlan?.id, indicatorPlan?.revision, indicatorScenario?.id, includeScenario, analysisArea]);
  useEffect(() => {
    if (plan && scenario) {
      try { localStorage.setItem(`urban-plan-scenario-${plan.id}`, scenario.id); } catch { /* Browser storage is optional. */ }
    }
  }, [plan, scenario]);
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
    try {
      const next = (await zoningRequest<{ plans: PlanSummary[] }>('', undefined, signal)).plans;
      setPlans(next);
      const available = new Set(next.map(item => item.id));
      setDisplayedPlans(current => Object.fromEntries(Object.entries(current).filter(([id]) => available.has(id))));
      setDisplayedPlanDetails(current => Object.fromEntries(Object.entries(current).filter(([id]) => available.has(id))));
      setError('');
    }
    catch (cause) { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'Unable to load plans'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, []);
  const togglePlanOnMap = async (id: string) => {
    if (displayedPlans[id]) {
      setDisplayedPlans(current => { const next = { ...current }; delete next[id]; return next; });
      if (lastDisplayedPlanId === id) setLastDisplayedPlanId(null);
      return;
    }
    if (loadingPlanId) return;
    setLoadingPlanId(id);
    try {
      const details = await zoningRequest<Plan>(`/${encodeURIComponent(id)}`);
      if (!removedPlanIds.current.has(id)) {
        setDisplayedPlans(current => ({ ...current, [id]: details.study_area }));
        setDisplayedPlanDetails(current => ({ ...current, [id]: details }));
        setLastDisplayedPlanId(id);
      }
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to show plan on map');
    } finally { setLoadingPlanId(null); }
  };
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [active, refresh]);

  const openPlan = async (id: string) => {
    const next = await run(() => zoningRequest<Plan>(`/${encodeURIComponent(id)}`));
    if (!next) return;
    let remembered: string | null = null;
    try { remembered = localStorage.getItem(`urban-plan-scenario-${next.id}`); } catch { /* Browser storage is optional. */ }
    setPlan(next); setScenarioId(next.scenarios.find(s => s.id === remembered)?.id ?? next.scenarios.find(s => s.kind === 'proposal')?.id ?? next.scenarios[0].id);
    setSelected([]); cancel(); zoomTo(next.study_area);
  };
  const execute = async (action: string, payload: Record<string, unknown> = {}, target = scenario?.id ?? null) => {
    if (!plan) return null;
    const next = await run(() => zoningRequest<Plan>(`/${plan.id}/commands`, {
      revision: plan.revision, scenario_id: target, action, payload,
    }));
    if (next) {
      setPlan(next); cancel();
      if (displayedPlans[next.id]) setDisplayedPlanDetails(current => ({ ...current, [next.id]: next }));
      setSelected(ids => ids.filter(id => next.scenarios.find(s => s.id === target)?.zones.some(z => z.id === id)));
      if (action === 'add_scenario') { setScenarioId(next.scenarios.at(-1)!.id); setSelected([]); }
      if (action === 'add_type' || action === 'duplicate_type') setTypeId(next.types.at(-1)!.id);
    }
    return next;
  };
  const development = useDevelopment(plan, scenario, sketch, setSketch, execute, setError);
  const leave = (action: () => void) => {
    if (busy || development.working) return;
    if (development.dirty) { leaveAction.current = action; setLeaving(true); }
    else action();
  };
  const resolveLeave = async (choice: 'save' | 'discard' | 'cancel') => {
    if (choice === 'cancel') { setLeaving(false); leaveAction.current = null; return; }
    if (choice === 'save' && !await development.save()) return;
    if (choice === 'discard') development.cancel();
    setLeaving(false); leaveAction.current?.(); leaveAction.current = null;
  };
  const setSection = (value: typeof section, after?: () => void) => leave(() => { setSelected([]); cancel(); setSectionState(value); if (value !== 'dashboard') setPanel('plans'); after?.(); });
  const create = async (name: string, description: string, horizon: number | null) => {
    const geometry = sketchGeometry(sketch);
    if (!geometry || geometry.type === 'LineString') { setError('Draw a study area with at least three points'); return; }
    const next = await run(() => zoningRequest<Plan>('', { name, description, horizon, study_area: geometry }));
    if (next) { setPlan(next); setScenarioId(next.scenarios[1].id); cancel(); zoomTo(next.study_area); void refresh(); }
  };
  const deletePlan = async (id: string, revision: number) => {
    const result = await run(() => deleteZoningPlan(id, revision).then(() => true));
    if (result) {
      removedPlanIds.current.add(id);
      if (plan?.id === id) { setPlan(null); setScenarioId(null); setSelected([]); cancel(); }
      setPlans(current => current.filter(item => item.id !== id));
      setDisplayedPlans(current => { const next = { ...current }; delete next[id]; return next; });
      setDisplayedPlanDetails(current => { const next = { ...current }; delete next[id]; return next; });
      if (lastDisplayedPlanId === id) setLastDisplayedPlanId(null);
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
    if (sketch.tool === 'analysis') {
      const geometry = sketchGeometry(sketch);
      if (!geometry || geometry.type === 'LineString') { setError('Draw at least three points'); return; }
      setAnalysisSelection({ planId: indicatorPlan?.id ?? null, geometry }); cancel(); return;
    }
    if (sketch.tool === 'building' || sketch.tool === 'edit-building') { await development.previewBuilding(); return; }
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
    if (tool === 'study') { setPlan(null); setScenarioId(null); setSelected([]); }
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
    leave(() => { setScenarioId(id); setPolicyState('preserve'); cancel(); setSelected([]); development.clearSelection(); });
  };
  const pick = (id: string | null, multiple: boolean) => {
    if (busy) return;
    setSelected(ids => !id ? [] : multiple ? ids.includes(id) ? ids.filter(i => i !== id) : [...ids, id] : [id]);
  };
  const close = (after?: () => void) => leave(() => { setPanel(null); cancel(); after?.(); });
  const acceptAssistant = async (binding: {plan_id?: string; scenario_id?: string; parcel_id?: string; building_id?: string}) => {
    if (!binding.plan_id || development.dirty) return;
    const next = await zoningRequest<Plan>(`/${encodeURIComponent(binding.plan_id)}`);
    setPlan(next); setScenarioId(binding.scenario_id ?? next.scenarios[1]?.id ?? next.scenarios[0].id);
    setPanel('plans'); setSectionState('development'); setSelected([]); cancel();
    development.adoptAssistantSelection(next.id,binding.scenario_id ?? next.scenarios[1]?.id ?? next.scenarios[0].id,binding.parcel_id,binding.building_id);
    if (binding.plan_id !== plan?.id) zoomTo(next.study_area);
    await refresh();
  };
  return { panel, setPanel, active, close, plan, plans, displayedPlans, displayedPlanScenes, loadingPlanId, togglePlanOnMap, scenario, indicatorPlan, indicatorScenario, chosenType, typeId, setTypeId, selected, pick,
    analyzing, analysisArea, includeScenario, setIncludeScenario, useStudyArea,
    indicatorScope, setIndicatorChart, indicatorChart: analyzing && indicatorChart?.scope === indicatorScope ? indicatorChart : null,
    sketch, setSketch, begin, cancel: development.dirty ? development.cancel : cancel, preview, policy, setPolicy, finish, confirm, readOnly, opacity, setOpacity,
    section, setSection, development, leaving, resolveLeave, leave, acceptAssistant,
    visible, setVisible, showParcels, setShowParcels, parcelAvailable, busy: busy || development.working || assistantBusy, loading, error, setError, focus, zoomTo, openPlan, execute, create, deletePlan, refresh, selectScenario,
    back: (after?: () => void) => leave(() => { setPlan(null); setSelected([]); cancel(); void refresh(); after?.(); }),
  };
}
export type ZoningWorkspace = ReturnType<typeof useZoning>;
