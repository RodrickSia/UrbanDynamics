import { useState } from 'react';
import { Combine, MousePointer2, Pentagon, Redo2, Scissors, Undo2, X } from 'lucide-react';
import { ActionDialog } from './Dialog';
import { areaText, sketchGeometry } from './geometry';
import type { ZoningWorkspace } from './useZoning';

export function ZoningToolbar({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [confirmStudy, setConfirmStudy] = useState(false);
  if (!w.plan) return null;
  const hasOne = w.selected.length === 1;
  return <div className={`zoning-tools solid-panel zoning-ui${w.sketch.tool ? ' is-editing' : ''}`} aria-label="Zoning tools">
    {!w.sketch.tool ? <>
      <div className="zoning-tool-rail">
        <button title="Select zones" aria-label="Select zones" aria-pressed={!w.sketch.tool} onClick={w.cancel}><MousePointer2 size={18}/></button>
        <button title="Draw zone" aria-label="Draw zone" disabled={w.readOnly || w.busy || !w.chosenType} onClick={() => w.begin('draw')}><Pentagon size={18}/></button>
        <button title="Split zone" aria-label="Split zone" disabled={w.readOnly || w.busy || !hasOne} onClick={() => w.begin('split')}><Scissors size={18}/></button>
        <button title="Merge zones" aria-label="Merge zones" disabled={w.readOnly || w.busy || w.selected.length < 2} onClick={() => void w.execute('merge', { zone_ids: w.selected })}><Combine size={18}/></button>
        <button title="Undo geometry" aria-label="Undo geometry" disabled={w.readOnly || w.busy || !w.scenario?.can_undo} onClick={() => void w.execute('undo')}><Undo2 size={18}/></button>
        <button title="Redo geometry" aria-label="Redo geometry" disabled={w.readOnly || w.busy || !w.scenario?.can_redo} onClick={() => void w.execute('redo')}><Redo2 size={18}/></button>
      </div>
    </> : <>
      <div className="zoning-row"><strong>{w.sketch.tool === 'edit-study' ? 'Edit study area' : w.sketch.tool === 'reshape' ? 'Edit zone vertices' : w.sketch.tool === 'split' ? 'Split selected zone' : `Draw ${w.chosenType?.code ?? 'zone'}`}</strong><button className="quiet-icon-button" aria-label="Cancel geometry edit" disabled={w.busy} onClick={w.cancel}><X size={18}/></button></div>
      <p>{w.sketch.geometry ? 'Drag a vertex. Click a midpoint to add; Shift-click a vertex to remove.' : w.sketch.tool === 'split' ? 'Click points to cut across the zone, then apply the split.' : 'Click to add points. Available parcel, road, water, and zoning edges snap within 10 pixels. Hold Ctrl to suspend snapping.'}</p>
      {!w.sketch.geometry && <small role="status">{w.sketch.points.length} points</small>}
      {w.preview && <div role="status" className="zoning-preview"><strong>Preview ready</strong><p>{w.preview.affected_ids.length} existing zones intersect · {areaText(w.preview.overlap_m2)}</p><p>Outside study area clipped: {areaText(w.preview.clipped_outside_m2)}</p></div>}
      <footer><button disabled={w.busy} onClick={w.cancel}>Cancel</button>{!w.sketch.geometry && <button disabled={w.busy || !w.sketch.points.length} onClick={() => w.setSketch({ ...w.sketch, points: w.sketch.points.slice(0, -1) })}>Undo point</button>}
        <button className="zoning-primary" disabled={w.busy || !sketchGeometry(w.sketch)} onClick={() => {
          if (w.sketch.tool === 'edit-study') setConfirmStudy(true);
          else if (w.preview) void w.confirm(); else void w.finish();
        }}>{w.busy ? 'Saving…' : w.sketch.tool === 'split' ? 'Apply split' : w.sketch.tool === 'edit-study' ? 'Update area' : w.preview ? 'Confirm zoning' : 'Preview'}</button></footer>
    </>}
    {confirmStudy && <ActionDialog title="Update study area?" message="Proposal zones will be clipped to this area in every scenario. Geometry undo history will reset. The reference snapshot stays unchanged." busy={w.busy} error={w.error} onClose={() => setConfirmStudy(false)}
      onConfirm={async () => !!await w.execute('study_area', { geometry: sketchGeometry(w.sketch), confirm: true })}/>}
  </div>;
}
