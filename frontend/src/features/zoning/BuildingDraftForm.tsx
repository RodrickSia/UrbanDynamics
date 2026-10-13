import type { ZoningWorkspace } from './useZoning';

export function BuildingDraftForm({ workspace: w, onView }: { workspace: ZoningWorkspace; onView?: (mode: '2d' | '3d') => void }) {
  const d = w.development;
  if (!d.draft) return null;
  return <form onSubmit={e => { e.preventDefault(); void d.save(); }}>
    <p role="status" className="zoning-badge">Unsaved proposal</p>
    <p className="zoning-muted">{w.sketch.geometry ? 'Drag vertices; click midpoints to add. Shift-click to remove.' : `${w.sketch.points.length} points · click to draw; Enter to preview.`} Ctrl disables snapping.</p>
    <fieldset disabled={w.busy} className="development-fieldset">
      <label>Building name<input value={d.draft.name} maxLength={120} required onChange={e => d.update({ name: e.target.value })}/></label>
      <div className="development-fields"><label>Floors<input type="number" min="1" max="200" required value={d.draft.floors} onChange={e => d.update({ floors: e.target.valueAsNumber })}/></label>
        <label>Floor height (m)<input type="number" min="0.1" max="20" step="any" required value={d.draft.floor_height} onChange={e => d.update({ floor_height: e.target.valueAsNumber })}/></label></div>
      <label>Space use<select value={d.draft.space_use_id} onChange={e => d.update({ space_use_id: e.target.value })}>
        {(d.data?.catalog.space_uses ?? []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className="zoning-checkbox"><input type="checkbox" checked={d.draft.counts_gfa} onChange={e => d.update({ counts_gfa: e.target.checked })}/>Counts towards GFA</label>
      <label className="zoning-checkbox"><input type="checkbox" checked={d.draft.counts_far} onChange={e => d.update({ counts_far: e.target.checked })}/>Counts towards FAR</label>
      <label className="zoning-checkbox"><input type="checkbox" checked={!!d.draft.demolish} onChange={e => d.update({ demolish: e.target.checked })}/>Hide baseline on this parcel</label>
      <footer><button type="button" onClick={d.cancel}>Cancel</button><button type="button" disabled={!d.input} onClick={() => void d.previewBuilding().then(value => { if (value) onView?.('3d'); })}>Preview</button>
        <button className="zoning-primary" disabled={!d.input}>Save proposal</button></footer>
    </fieldset>
  </form>;
}
