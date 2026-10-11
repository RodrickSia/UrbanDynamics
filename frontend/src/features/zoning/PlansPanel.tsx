import { useState } from 'react';
import { ArrowDown, ArrowUp, Copy, Pencil, Plus, Trash2 } from 'lucide-react';
import { ActionDialog } from './Dialog';
import { areaText, sketchGeometry } from './geometry';
import { TypeEditor } from './TypeEditor';
import type { PlanSummary, ZoneType } from './types';
import type { ZoningWorkspace } from './useZoning';

export function PlansPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [horizon, setHorizon] = useState('');
  const [filter, setFilter] = useState('');
  const [editingType, setEditingType] = useState<ZoneType | 'new' | null>(null);
  const [typeAction, setTypeAction] = useState<{ type: ZoneType; action: 'delete_type' | 'duplicate_type' } | null>(null);
  const [deletingPlan, setDeletingPlan] = useState<PlanSummary | null>(null);
  if (!w.plan) return <>
    {w.sketch.tool === 'study' ? <form onSubmit={e => { e.preventDefault(); void w.create(name, description, horizon ? Number(horizon) : null); }}>
      <h3>New zoning plan</h3><label>Plan name<input autoFocus required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label>
      <label>Description<textarea maxLength={2000} value={description} onChange={e => setDescription(e.target.value)}/></label>
      <label>Planning horizon<input type="number" min={2020} max={2200} placeholder="Optional" value={horizon} onChange={e => setHorizon(e.target.value)}/></label>
      <label className="zoning-check"><input type="checkbox" disabled={!w.parcelAvailable} checked={w.showParcels && w.parcelAvailable} onChange={e => w.setShowParcels(e.target.checked)}/>Show parcel outlines</label>
      {!w.parcelAvailable && <p className="zoning-muted">Parcel boundaries are unavailable here.</p>}
      <p>Click the map to draw a small study area in Thủ Đức. Nearby parcel, road, and water geometry snaps within 10 px when available on the map. Hold Ctrl to draw freely; Backspace removes the last point.</p>
      <p role="status">{w.sketch.points.length} points · {sketchGeometry(w.sketch) ? 'Ready to save' : 'At least 3 points needed'}</p>
      <footer><button type="button" onClick={w.cancel} disabled={w.busy}>Cancel</button><button className="zoning-primary" disabled={w.busy || !sketchGeometry(w.sketch)}>Create plan</button></footer>
    </form> : <>
      <button className="zoning-primary zoning-wide" disabled={w.busy} onClick={() => {
        w.begin('study'); w.zoomTo({ type: 'Polygon', coordinates: [[[106.735, 10.80], [106.79, 10.80], [106.79, 10.855], [106.735, 10.855], [106.735, 10.80]]] });
      }}><Plus size={17}/>New plan</button>
      {w.loading && <p role="status">Loading plans…</p>}
      {!w.loading && !w.plans.length && <div className="zoning-empty"><h3>A place for your next proposal</h3><p>Draw a study area, define zoning rules, and explore alternative scenarios.</p></div>}
      <ul className="zoning-plan-list">{w.plans.map(p => <li key={p.id}><button disabled={w.busy} onClick={() => void w.openPlan(p.id)}><strong>{p.name}</strong><span>{areaText(p.area_m2)} · Draft</span><small>{new Date(p.updated_at).toLocaleDateString()}</small></button><button className="zoning-plan-delete" aria-label={`Delete plan ${p.name}`} title="Delete plan" disabled={w.busy} onClick={() => setDeletingPlan(p)}><Trash2 size={16}/></button></li>)}</ul>
      <button className="zoning-wide" disabled={w.loading} onClick={() => void w.refresh()}>Refresh plans</button>
      {deletingPlan && <ActionDialog title="Delete plan?" message={`Delete “${deletingPlan.name}” and all of its scenarios? This cannot be undone.`}
        busy={w.busy} error={w.error} onClose={() => setDeletingPlan(null)} onConfirm={async () => !!await w.deletePlan(deletingPlan.id, deletingPlan.revision)}/>}
    </>}
  </>;
  const plan = w.plan;
  const reorder = (index: number, direction: number) => {
    const ids = plan.types.map(t => t.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    void w.execute('reorder_types', { ids });
  };
  return <>
    <div className="zoning-plan-meta"><span className="zoning-badge">Draft proposal</span><span>{areaText(plan.area_m2)}</span></div>
    <p className="zoning-muted">{w.scenario?.kind === 'reference' ? plan.baseline.source : 'Explore proposed controls without changing reference data.'}</p>
    <div className="zoning-row"><button onClick={() => w.zoomTo(plan.study_area)}>Locate plan</button><button disabled={w.busy || plan.scenarios.some(s => s.kind === 'proposal' && s.locked)} onClick={() => w.begin('edit-study')}>Edit study area</button></div>
    <label className="zoning-check"><input type="checkbox" disabled={!w.parcelAvailable} checked={w.showParcels && w.parcelAvailable} onChange={e => w.setShowParcels(e.target.checked)}/>Show parcel outlines in study area</label>
    {!w.parcelAvailable && <p className="zoning-muted">Parcel boundaries are unavailable here.</p>}
    <h3>Zoning types <button className="quiet-icon-button" disabled={w.busy || !!w.sketch.tool} onClick={() => { w.setError(''); setEditingType('new'); }} aria-label="Add zoning type"><Plus size={18}/></button></h3>
    <input aria-label="Search zoning types" placeholder="Search type or code" value={filter} onChange={e => setFilter(e.target.value)}/>
    {!plan.types.length && <p className="zoning-muted">Add your first zoning type, then draw its boundary on the map.</p>}
    <ul className="zoning-type-list">{plan.types.map((type, index) => {
      if (!`${type.code} ${type.name}`.toLowerCase().includes(filter.toLowerCase())) return null;
      const area = w.scenario?.zones.filter(z => z.type_id === type.id).reduce((sum, z) => sum + z.area_m2, 0) ?? 0;
      return <li key={type.id} data-selected={w.chosenType?.id === type.id}>
        <button className="zoning-type-choice" disabled={!!w.sketch.tool || w.busy} aria-pressed={w.chosenType?.id === type.id} onClick={() => w.setTypeId(type.id)}>
          <span className="zoning-swatch" style={{ backgroundColor: type.color }}/><span><strong>{type.code} · {type.name}</strong><small>{areaText(area)} · FAR {type.far ?? 'Unknown'}</small></span>
        </button><div className="zoning-type-actions">
          <button aria-label={`Edit ${type.code}`} onClick={() => { w.setError(''); setEditingType(type); }} disabled={w.busy}><Pencil size={14}/></button>
          <button aria-label={`Duplicate ${type.code}`} onClick={() => setTypeAction({ type, action: 'duplicate_type' })} disabled={w.busy}><Copy size={14}/></button>
          <button aria-label={`Delete ${type.code}`} onClick={() => setTypeAction({ type, action: 'delete_type' })} disabled={w.busy}><Trash2 size={14}/></button>
          <button aria-label={`Move ${type.code} up`} onClick={() => reorder(index, -1)} disabled={w.busy || index === 0}><ArrowUp size={14}/></button>
          <button aria-label={`Move ${type.code} down`} onClick={() => reorder(index, 1)} disabled={w.busy || index === plan.types.length - 1}><ArrowDown size={14}/></button>
        </div>
      </li>;
    })}</ul>
    <label className="zoning-check"><input type="checkbox" checked={w.visible} onChange={e => w.setVisible(e.target.checked)}/>Show zoning</label>
    <label>Fill opacity <span>{Math.round(w.opacity * 100)}%</span><input type="range" min={0} max={.8} step={.05} value={w.opacity} onChange={e => w.setOpacity(Number(e.target.value))}/></label>
    <details><summary>Reference snapshot</summary><p>{plan.baseline.source}</p><p className="zoning-muted">Captured {new Date(plan.baseline.captured_at).toLocaleString()}</p><p className="zoning-muted">{plan.baseline.version}</p></details>
    <button className="zoning-delete-action" disabled={w.busy} onClick={() => setDeletingPlan(plan)}><Trash2 size={16}/>Delete plan</button>
    {deletingPlan && <ActionDialog title="Delete plan?" message={`Delete “${deletingPlan.name}” and all of its scenarios? This cannot be undone.`}
      busy={w.busy} error={w.error} onClose={() => setDeletingPlan(null)} onConfirm={async () => !!await w.deletePlan(deletingPlan.id, deletingPlan.revision)}/>}
    {editingType && <TypeEditor value={editingType === 'new' ? undefined : editingType} shared={editingType !== 'new' && plan.scenarios.filter(s => s.zones.some(z => z.type_id === editingType.id)).length > 1}
      busy={w.busy} error={w.error} onClose={() => setEditingType(null)} onSave={async (value, confirm_shared) => !!await w.execute(editingType === 'new' ? 'add_type' : 'edit_type', {
        type: value, ...(editingType === 'new' ? {} : { id: editingType.id, confirm_shared }),
      })}/>}
    {typeAction && <ActionDialog title={typeAction.action === 'delete_type' ? 'Delete zoning type?' : 'Duplicate zoning type'} initial={typeAction.action === 'duplicate_type' ? `${typeAction.type.name} copy` : undefined}
      message={typeAction.action === 'delete_type' ? 'Only unused types can be removed. Types referenced by undo history are retained.' : 'Creates an independent proposal type with copied rules.'}
      busy={w.busy} error={w.error} onClose={() => setTypeAction(null)} onConfirm={async value => !!await w.execute(typeAction.action, { id: typeAction.type.id, name: value, code: `${typeAction.type.code.slice(0, 12)}-${plan.types.length + 1}` })}/>}
  </>;
}
