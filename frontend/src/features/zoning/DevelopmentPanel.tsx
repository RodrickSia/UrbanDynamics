import { useState } from 'react';
import { Copy, Pencil, Plus, Redo2, Trash2, Undo2 } from 'lucide-react';
import { ActionDialog } from './Dialog';
import { areaText } from './geometry';
import { BuildingDraftForm } from './BuildingDraftForm';
import { DevelopmentValues } from './DevelopmentValues';
import type { ZoningWorkspace } from './useZoning';

export function DevelopmentPanel({ workspace: w, onView }: { workspace: ZoningWorkspace; onView?: (mode: '2d' | '3d') => void }) {
  const d = w.development;
  const [confirm, setConfirm] = useState<'delete' | 'demolish' | 'restore' | null>(null);
  const [coverage, setCoverage] = useState(40), [setback, setSetback] = useState(3);
  const [floors, setFloors] = useState(2), [floorHeight, setFloorHeight] = useState(3.2);
  const selected = w.scenario?.buildings?.find(b => b.id === d.selectedBuilding);
  const masked = w.scenario?.demolition_masks?.some(m => m.parcel_id === d.parcelId);
  const confirmation = d.deleteRequested ? 'delete' : confirm;
  const report = d.preview ?? (!d.draft ? d.data : null);
  return <section aria-label="Development editor">
    <div className="zoning-row"><h3>Development</h3><span className="zoning-badge">{w.readOnly ? 'Read-only' : 'Proposal'}</span></div>
    <div className="development-actions">
      <button onClick={() => onView?.('2d')}>2D</button><button onClick={() => onView?.('3d')}>3D</button>
      <button title="Undo development" aria-label="Undo development" disabled={w.busy || w.readOnly || d.dirty || !w.scenario?.can_undo_development} onClick={() => void w.execute('undo_development')}><Undo2 size={16}/></button>
      <button title="Redo development" aria-label="Redo development" disabled={w.busy || w.readOnly || d.dirty || !w.scenario?.can_redo_development} onClick={() => void w.execute('redo_development')}><Redo2 size={16}/></button>
    </div>
    {!d.parcelId && <p className="zoning-muted">Select a parcel on the map.</p>}
    {!w.parcelAvailable && !d.parcel && <p role="status">Parcel data unavailable. Saved proposals remain accessible.</p>}
    {d.loading && <p role="status">Loading parcel…</p>}
    {d.error && <div role="alert"><p>{d.error}</p><button onClick={d.retry}>Retry parcel</button></div>}
    {d.parcel && <>
      <div className="development-parcel"><strong>Parcel {d.parcel.id}</strong><span>{d.parcel.land_use ?? 'Unknown use'} · {areaText(d.parcel.area_m2)}</span></div>
      {!d.draft && !w.readOnly && <>
        <div className="development-actions"><button className="zoning-primary" disabled={w.busy} onClick={() => { d.begin(); onView?.('2d'); }}><Plus size={16}/> Draw building</button>
          <button disabled={w.busy} onClick={() => setConfirm(masked ? 'restore' : 'demolish')}>{masked ? 'Restore baseline' : 'Demolish parcel'}</button></div>
        <details><summary>Apply building type</summary>
          <p className="zoning-muted">Low-rise v1 · user assumptions</p>
          <form onSubmit={e => { e.preventDefault(); void d.generate(coverage, setback, floors, floorHeight); }}>
            <div className="development-fields"><label>Coverage (%)<input type="number" min="1" max="100" step="any" required value={coverage} onChange={e => setCoverage(e.target.valueAsNumber)}/></label>
              <label>Setback (m)<input type="number" min="0" max="1000" step="any" required value={setback} onChange={e => setSetback(e.target.valueAsNumber)}/></label>
              <label>Floors<input type="number" min="1" max="200" required value={floors} onChange={e => setFloors(e.target.valueAsNumber)}/></label>
              <label>Floor height (m)<input type="number" min="0.1" max="20" step="any" required value={floorHeight} onChange={e => setFloorHeight(e.target.valueAsNumber)}/></label></div>
            <button disabled={w.busy}>Preview type</button>
          </form>
        </details>
      </>}
      {selected && !d.draft && <div className="development-building"><h3>{selected.name}</h3><p>{selected.floors} floors · {selected.height_m.toFixed(1)} m</p>
        <div className="development-actions"><button disabled={w.readOnly || w.busy} onClick={() => { d.begin(selected); onView?.('2d'); }}><Pencil size={16}/>Edit</button>
          <button disabled={w.readOnly || w.busy} onClick={() => { d.begin(selected, true); onView?.('2d'); }}><Copy size={16}/>Duplicate</button>
          <button aria-label="Delete building" title="Delete building" disabled={w.readOnly || w.busy} onClick={() => setConfirm('delete')}><Trash2 size={16}/></button></div></div>}
      <BuildingDraftForm workspace={w} onView={onView}/>
      {report && <DevelopmentValues report={report}/>}
      <p className="zoning-muted">Concept massing · approximate terrain anchor. Baseline heights unverified.</p>
      {masked && <p className="zoning-muted">Parcel demolition is scenario-only. Raster imagery and objects without stable IDs may remain visible.</p>}
    </>}
    {!!w.scenario?.buildings?.length && <><h3>Proposed buildings</h3><ul className="development-list">{w.scenario.buildings.map(b => <li key={b.id}><button disabled={d.dirty || w.busy} aria-pressed={b.id === d.selectedBuilding} onClick={() => { d.pickBuilding(b.id); w.zoomTo(b.geometry); }}>{b.name}<small>{b.floors} floors · {b.height_m.toFixed(1)} m</small></button></li>)}</ul></>}
    {confirmation && <ActionDialog title={confirmation === 'delete' ? 'Delete proposed building?' : confirmation === 'demolish' ? 'Demolish this parcel?' : 'Restore baseline?'}
      message={confirmation === 'delete' ? 'Remove this proposal from the active scenario.' : 'Only baseline visibility in this scenario changes. Source geometry is retained.'}
      busy={w.busy} error={w.error} onClose={() => { setConfirm(null); d.setDeleteRequested(false); }} onConfirm={async () => !!await w.execute(confirmation === 'delete' ? 'delete_building' : confirmation === 'demolish' ? 'demolish_parcel' : 'restore_parcel',
        confirmation === 'delete' ? { id: selected?.id, confirm: true } : { parcel_id: d.parcelId, confirm: true })}/>}
  </section>;
}
