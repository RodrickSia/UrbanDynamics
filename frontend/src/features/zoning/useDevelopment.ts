import { useEffect, useRef, useState } from 'react';
import { ZoningRequestError, zoningRequest } from './api';
import { buildingInput, type BuildingInput, type DevelopmentPreview, type ParcelDevelopment, type ProposedBuilding } from './developmentTypes';
import { sketchGeometry } from './geometry';
import type { Plan, Scenario, Sketch } from './types';
import type { FeatureCollection } from 'geojson';

const EMPTY: Sketch = { tool: null, geometry: null, points: [] };
export function useDevelopment(plan: Plan | null, scenario: Scenario | null, sketch: Sketch,
  setSketch: (s: Sketch) => void, execute: (action: string, payload?: Record<string, unknown>) => Promise<Plan | null>,
  setError: (error: string) => void) {
  const scope = `${plan?.id}/${scenario?.id}`;
  const [selection, setSelection] = useState({ scope: '', parcelId: '', buildingId: '' });
  const [response, setResponse] = useState<{ key: string; value?: ParcelDevelopment; error?: string; mapContextAccepted?: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  const [mapped, setMapped] = useState<{ scope: string; parcelId: string; buildings: FeatureCollection }>();
  const [draftState, setDraftState] = useState<{ scope: string; value: BuildingInput } | null>(null);
  const [previewState, setPreviewState] = useState<{ key: string; value: DevelopmentPreview } | null>(null);
  const [working, setWorking] = useState(false);
  const [deleteRequested, setDeleteRequested] = useState(false);
  const sequence = useRef(0);
  const pending = useRef(false);
  const parcelId = selection.scope === scope ? selection.parcelId : '';
  const selectedBuilding = selection.scope === scope ? selection.buildingId : '';
  const mapBuildings = mapped?.scope === scope && mapped.parcelId === parcelId ? mapped.buildings : undefined;
  const mapKey = JSON.stringify(mapBuildings ?? null);
  const requestKey = `${scope}/${plan?.revision}/${parcelId}/${retry}/${mapKey}`;
  const draft = draftState?.scope === scope ? draftState.value : null;
  const geometry = sketchGeometry(sketch);
  const input = draft && geometry && geometry.type !== 'LineString' ? { ...draft, geometry } : null;
  const inputKey = JSON.stringify(input);
  const preview = previewState?.key === `${requestKey}/${inputKey}` ? previewState.value : null;
  const data = response?.key === requestKey ? response.value : undefined;
  const error = response?.key === requestKey ? response.error : undefined;
  // Retain the canonical parcel while supplementing its report with loaded map tiles.
  const parcel = data?.parcel ?? (response?.value?.parcel.id === parcelId && response.key.startsWith(`${scope}/`) ? response.value.parcel : null)
    ?? (parcelId ? plan?.parcels?.[parcelId] : null) ?? null;
  const readOnly = !scenario || scenario.locked || scenario.kind === 'reference';
  useEffect(() => {
    if (!plan || !scenario || !parcelId) return;
    const controller = new AbortController();
    const basePath = `/${plan.id}/development/parcels/${encodeURIComponent(parcelId)}`;
    const path = `${basePath}?scenario_id=${scenario.id}`;
    const read = async () => {
      if (!mapBuildings) return { value: await zoningRequest<ParcelDevelopment>(path, undefined, controller.signal), mapContextAccepted: false };
      try {
        return { value: await zoningRequest<ParcelDevelopment>(`${basePath}/baseline?scenario_id=${scenario.id}`, mapBuildings, controller.signal), mapContextAccepted: true };
      } catch (cause) {
        if (!(cause instanceof ZoningRequestError) || cause.status !== 422) throw cause;
        // Loaded basemap fragments are optional context. Keep the canonical
        // zoning site usable even when one source footprint fails validation.
        return { value: await zoningRequest<ParcelDevelopment>(path, undefined, controller.signal), mapContextAccepted: false };
      }
    };
    void read()
      .then(({ value, mapContextAccepted }) => { if (!controller.signal.aborted) setResponse({ key: requestKey, value, mapContextAccepted }); })
      .catch(cause => { if (!controller.signal.aborted) setResponse({ key: requestKey, error: cause.message }); });
    return () => controller.abort();
  }, [plan, scenario, parcelId, requestKey, mapBuildings]);
  useEffect(() => {
    if (!draft) return;
    const prevent = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', prevent);
    return () => window.removeEventListener('beforeunload', prevent);
  }, [draft]);
  const cancel = () => { sequence.current++; setDraftState(null); setPreviewState(null); setSketch(EMPTY); };
  const clearSelection = () => { setSelection({ scope: '', parcelId: '', buildingId: '' }); setDeleteRequested(false); };
  const pickParcel = (id: string) => { if (!draft && !working) setSelection({ scope, parcelId: id, buildingId: '' }); };
  const pickBuilding = (id: string) => {
    const b = scenario?.buildings?.find(item => item.id === id);
    if (b && !draft && !working) setSelection({ scope, parcelId: b.parcel_id, buildingId: id });
  };
  const begin = (source?: ProposedBuilding, duplicate = false) => {
    if (!parcel || readOnly || working) return;
    const value: BuildingInput = source ? { ...buildingInput(source), id: duplicate ? null : source.id,
      origin_id: duplicate ? source.id : source.origin_id, name: duplicate ? `${source.name} copy` : source.name } : {
      parcel_id: parcel.id, geometry: parcel.geometry, name: 'Proposed building', floors: 2, floor_height: 3.2,
      space_use_id: 'residential', counts_gfa: true, counts_far: true, demolish: false,
    };
    setDraftState({ scope, value }); setPreviewState(null); setError('');
    setSketch({ tool: source ? 'edit-building' : 'building', geometry: source ? structuredClone(source.geometry) : null, points: [] });
  };
  const update = (patch: Partial<BuildingInput>) => {
    if (draft && !working) {
      // Removed floors must not leave hidden overrides that reappear on save.
      const value = { ...draft, ...patch };
      if (patch.floors !== undefined && Number.isInteger(patch.floors) && patch.floors >= 1)
        value.floor_overrides = value.floor_overrides?.filter(floor => floor.floor <= value.floors);
      setDraftState({ scope, value }); setPreviewState(null);
    }
  };
  const previewBuilding = async () => {
    if (!plan || !scenario || !input || pending.current) { if (!input) setError('Draw at least three points'); return null; }
    pending.current = true; setWorking(true); setError('');
    const ticket = ++sequence.current;
    try {
      const value = await zoningRequest<DevelopmentPreview>(`/${plan.id}/preview`, {
        revision: plan.revision, scenario_id: scenario.id, action: 'save_building', payload: input });
      if (ticket !== sequence.current) return null;
      setPreviewState({ key: `${requestKey}/${inputKey}`, value });
      // Freeze the ring for vertex editing once it is completed.
      setSketch({ tool: 'edit-building', geometry: input.geometry, points: [] });
      return value;
    } catch (cause) { if (ticket === sequence.current) setError(cause instanceof Error ? cause.message : 'Preview unavailable'); return null; }
    finally { pending.current = false; setWorking(false); }
  };
  const generate = async (coverage: number, setback: number, floors: number, floorHeight: number) => {
    if (!plan || !scenario || !parcel || readOnly || pending.current) return;
    pending.current = true; setWorking(true); setError('');
    const ticket = ++sequence.current;
    try {
      const value = await zoningRequest<DevelopmentPreview>(`/${plan.id}/preview`, { revision: plan.revision,
        scenario_id: scenario.id, action: 'generate_building', payload: { parcel_id: parcel.id, coverage, setback,
          floors, floor_height: floorHeight, space_use_id: 'residential' } });
      if (ticket !== sequence.current) return;
      const next = { ...buildingInput(value.building), id: null, demolish: true };
      setDraftState({ scope, value: next });
      setSketch({ tool: 'edit-building', geometry: next.geometry, points: [] });
      setPreviewState({ key: `${requestKey}/${JSON.stringify(next)}`, value });
    } catch (cause) { if (ticket === sequence.current) setError(cause instanceof Error ? cause.message : 'Generation unavailable'); }
    finally { pending.current = false; setWorking(false); }
  };
  const save = async () => {
    if (!input || working) { if (!input) setError('Draw at least three points before saving'); return false; }
    const next = await execute('save_building', { ...input });
    if (!next) return false;
    const saved = next.scenarios.find(s => s.id === scenario?.id)?.buildings?.at(-1);
    cancel(); if (saved) setSelection({ scope, parcelId: saved.parcel_id, buildingId: saved.id });
    return true;
  };
  return { parcel, parcelId, selectedBuilding, data, error, loading: !!parcelId && !data && !error,
    adoptAssistantSelection: (planId: string, scenarioId: string, parcelId = '', buildingId = '') =>
      setSelection({scope:`${planId}/${scenarioId}`,parcelId,buildingId}),
    mapBuildings: response?.key === requestKey && response.mapContextAccepted ? mapBuildings : undefined,
    onBaseline: (id: string, buildings: FeatureCollection) => {
      if (id === parcelId) setMapped(previous => previous?.scope === scope && previous.parcelId === id
        && JSON.stringify(previous.buildings) === JSON.stringify(buildings) ? previous : { scope, parcelId: id, buildings });
    },
    retry: () => setRetry(n => n + 1), draft, input, preview, working, dirty: !!draft,
    deleteRequested, setDeleteRequested,
    pickParcel, pickBuilding, clearSelection, begin, update, cancel, previewBuilding, generate, save };
}
