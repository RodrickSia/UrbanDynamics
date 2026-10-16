import { useState } from 'react';
import { Eye, EyeOff, Plus } from 'lucide-react';
import { ActionDialog } from './Dialog';
import { areaText, sketchGeometry } from './geometry';
import type { PlanSummary } from './types';
import type { ZoningWorkspace } from './useZoning';
import { SwipeDeletePlan } from './SwipeDeletePlan';

export function PlansPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [horizon, setHorizon] = useState('');
  const [deletingPlan, setDeletingPlan] = useState<PlanSummary | null>(null);
  if (w.sketch.tool === 'study') return <form onSubmit={e => { e.preventDefault(); void w.create(name, description, horizon ? Number(horizon) : null); }}>
    <h3>New plan</h3>
    <label>Plan name<input autoFocus required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label>
    <label>Description<textarea maxLength={2000} value={description} onChange={e => setDescription(e.target.value)}/></label>
    <label>Planning horizon<input type="number" min={2020} max={2200} placeholder="Optional" value={horizon} onChange={e => setHorizon(e.target.value)}/></label>
    <label className="zoning-check"><input type="checkbox" disabled={!w.parcelAvailable} checked={w.showParcels && w.parcelAvailable} onChange={e => w.setShowParcels(e.target.checked)}/>Show parcel outlines</label>
    {!w.parcelAvailable && <p className="zoning-muted">Parcel boundaries unavailable here.</p>}
    <p className="zoning-muted">Draw the study area on the map. Hold Ctrl to pause snapping; Backspace removes a point.</p>
    <p role="status">{w.sketch.points.length} points · {sketchGeometry(w.sketch) ? 'Ready' : 'At least 3 needed'}</p>
    <footer><button type="button" onClick={w.cancel} disabled={w.busy}>Cancel</button><button className="zoning-primary" disabled={w.busy || !sketchGeometry(w.sketch)}>Create plan</button></footer>
  </form>;
  return <>
    <button className="zoning-primary zoning-wide" disabled={w.busy} onClick={() => w.begin('study')}><Plus size={17}/>New plan</button>
    {w.loading && <p role="status">Loading plans…</p>}
    {!w.loading && !w.plans.length && <div className="zoning-empty"><h3>No plans yet</h3><p>Draw a study area to begin.</p></div>}
    <ul className="zoning-plan-list">{w.plans.map(p => <li key={p.id} data-selected={w.plan?.id === p.id}>
      <SwipeDeletePlan name={p.name} disabled={w.busy} onDelete={() => setDeletingPlan(p)}>
        <button className="zoning-plan-open" disabled={w.busy} aria-current={w.plan?.id === p.id ? 'true' : undefined} onClick={() => void w.openPlan(p.id)}>
          <strong>{p.name}</strong><span>{areaText(p.area_m2)}</span><small>{new Date(p.updated_at).toLocaleDateString()}</small>
        </button>
        <button className="zoning-plan-visibility" aria-label={`${w.displayedPlans[p.id] ? 'Hide' : 'Show'} plan ${p.name} on map`}
          aria-pressed={!!w.displayedPlans[p.id]} aria-busy={w.loadingPlanId === p.id}
          data-visible={!!w.displayedPlans[p.id]} title={w.displayedPlans[p.id] ? 'Hide on map' : 'Show on map'}
          disabled={w.busy} onClick={() => void w.togglePlanOnMap(p.id)}>
          <span className="zoning-eye-icons" aria-hidden="true"><Eye size={18}/><EyeOff size={18}/></span>
        </button>
      </SwipeDeletePlan>
    </li>)}</ul>
    {deletingPlan && <ActionDialog title="Delete plan?" message={`Delete “${deletingPlan.name}” and all scenarios? This cannot be undone.`}
      busy={w.busy} error={w.error} onClose={() => setDeletingPlan(null)} onConfirm={async () => !!await w.deletePlan(deletingPlan.id, deletingPlan.revision)}/>}
  </>;
}
