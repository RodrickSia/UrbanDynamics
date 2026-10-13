import { useState } from 'react';
import { ArrowDown, ArrowUp, Copy, Pencil, Plus, Trash2 } from 'lucide-react';
import { ActionDialog } from './Dialog';
import { areaText } from './geometry';
import { CurrentParcelUse } from './CurrentParcelUse';
import { TypeEditor } from './TypeEditor';
import { ZoneInspector } from './ZoneInspector';
import type { ZoneType } from './types';
import type { ZoningWorkspace } from './useZoning';

export function PlanZoningPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [filter, setFilter] = useState('');
  const [editingType, setEditingType] = useState<ZoneType | 'new' | null>(null);
  const [typeAction, setTypeAction] = useState<{ type: ZoneType; action: 'delete_type' | 'duplicate_type' } | null>(null);
  const plan = w.plan, scenario = w.scenario;
  if (!plan || !scenario) return null;
  if (scenario.kind === 'reference') return <>
    <CurrentParcelUse plan={plan}/>
    <label className="zoning-check"><input type="checkbox" disabled={!w.parcelAvailable} checked={w.showParcels && w.parcelAvailable}
      onChange={e => w.setShowParcels(e.target.checked)}/>Show parcel outlines</label>
  </>;
  const assigned = scenario.zones.reduce((sum, zone) => sum + zone.area_m2, 0);
  const unassigned = Math.max(0, plan.area_m2 - assigned);
  const reorder = (index: number, direction: number) => {
    const ids = plan.types.map(t => t.id);
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    void w.execute('reorder_types', { ids });
  };
  return <>
    <details><summary>Current land use</summary><CurrentParcelUse plan={plan}/></details>
    <section className="zoning-distribution" aria-label="Zoning in scenario">
      <h3>Zoning in scenario</h3>
      <div className="zoning-area-strip" role="img" aria-label={`${areaText(assigned)} zoned, ${areaText(unassigned)} unassigned in ${scenario.name}`}>
        {scenario.zones.map(zone => <span key={zone.id} style={{ flexGrow: zone.area_m2 / plan.area_m2,
          backgroundColor: plan.types.find(t => t.id === zone.type_id)?.color ?? '#94a3b8' }}
          title={`${plan.types.find(t => t.id === zone.type_id)?.code ?? 'Unknown'} · ${areaText(zone.area_m2)}`}/>)}
        {unassigned > 0 && <span className="zoning-area-unassigned" style={{ flexGrow: unassigned / plan.area_m2 }} title={`Unassigned · ${areaText(unassigned)}`}/>}
      </div>
      <div className="zoning-distribution-caption"><span>{areaText(assigned)} assigned</span><span>Study area: {areaText(plan.area_m2)}</span></div>
    </section>
    <label>Overlap policy<select disabled={w.readOnly || w.busy} value={w.policy} onChange={e => w.setPolicy(e.target.value as 'preserve' | 'replace')}>
      <option value="preserve">Preserve existing</option><option value="replace">Replace underneath</option>
    </select></label>
    <h3>Zoning types <button className="quiet-icon-button" disabled={w.busy || !!w.sketch.tool} onClick={() => { w.setError(''); setEditingType('new'); }} aria-label="Add zoning type"><Plus size={18}/></button></h3>
    <input aria-label="Search zoning types" placeholder="Search type or code" value={filter} onChange={e => setFilter(e.target.value)}/>
    {!plan.types.length && <p className="zoning-muted">Add a type, then draw a zone.</p>}
    <ul className="zoning-type-list">{plan.types.map((type, index) => {
      if (!`${type.code} ${type.name}`.toLowerCase().includes(filter.toLowerCase())) return null;
      const area = scenario.zones.filter(z => z.type_id === type.id).reduce((sum, z) => sum + z.area_m2, 0);
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
    {w.selected.length > 0 && <ZoneInspector workspace={w}/>}
    {editingType && <TypeEditor value={editingType === 'new' ? undefined : editingType} shared={editingType !== 'new' && plan.scenarios.filter(s => s.zones.some(z => z.type_id === editingType.id)).length > 1}
      busy={w.busy} error={w.error} onClose={() => setEditingType(null)} onSave={async (value, confirm_shared) => !!await w.execute(editingType === 'new' ? 'add_type' : 'edit_type', {
        type: value, ...(editingType === 'new' ? {} : { id: editingType.id, confirm_shared }),
      })}/>}
    {typeAction && <ActionDialog title={typeAction.action === 'delete_type' ? 'Delete zoning type?' : 'Duplicate zoning type'} initial={typeAction.action === 'duplicate_type' ? `${typeAction.type.name} copy` : undefined}
      message={typeAction.action === 'delete_type' ? 'Only unused types can be removed.' : 'Creates an independent proposal type.'}
      busy={w.busy} error={w.error} onClose={() => setTypeAction(null)} onConfirm={async value => !!await w.execute(typeAction.action, { id: typeAction.type.id, name: value, code: `${typeAction.type.code.slice(0, 12)}-${plan.types.length + 1}` })}/>}
  </>;
}
