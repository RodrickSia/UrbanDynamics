import { useState } from 'react';
import { ActionDialog } from './Dialog';
import { areaText } from './geometry';
import type { ZoningWorkspace } from './useZoning';
import { SwipeDeletePlan } from './SwipeDeletePlan';

export function PlanInfoPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [deleting, setDeleting] = useState(false);
  const plan = w.plan;
  if (!plan) return null;
  return <>
    <dl className="zoning-plan-details">
      <div><dt>Plan name</dt><dd>{plan.name}</dd></div>
      <div><dt>Description</dt><dd>{plan.description || '—'}</dd></div>
      <div><dt>Planning horizon</dt><dd>{plan.horizon ?? '—'}</dd></div>
      <div><dt>Study area</dt><dd>{areaText(plan.area_m2)}</dd></div>
    </dl>
    <label className="zoning-check"><input type="checkbox" disabled={!w.parcelAvailable} checked={w.showParcels && w.parcelAvailable} onChange={e => w.setShowParcels(e.target.checked)}/>Show parcel outlines</label>
    {!w.parcelAvailable && <p className="zoning-muted">Parcel boundaries unavailable here.</p>}
    <details><summary>Reference snapshot</summary><p>{plan.baseline.source}</p><p className="zoning-muted">{new Date(plan.baseline.captured_at).toLocaleString()}</p></details>
    <SwipeDeletePlan name={plan.name} disabled={w.busy} onDelete={() => setDeleting(true)}>
      <span className="zoning-swipe-prompt">Swipe left to delete plan</span>
    </SwipeDeletePlan>
    {deleting && <ActionDialog title="Delete plan?" message={`Delete “${plan.name}” and all scenarios? This cannot be undone.`}
      busy={w.busy} error={w.error} onClose={() => setDeleting(false)} onConfirm={async () => !!await w.deletePlan(plan.id, plan.revision)}/>}
  </>;
}
