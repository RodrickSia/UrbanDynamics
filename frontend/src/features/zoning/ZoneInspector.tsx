import { X } from 'lucide-react';
import { useState } from 'react';
import { ActionDialog } from './Dialog';
import { areaText } from './geometry';
import { RULE_FIELDS } from './types';
import type { ZoningWorkspace } from './useZoning';

export function ZoneInspector({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [deleting, setDeleting] = useState(false);
  const zone = w.scenario?.zones.find(z => z.id === w.selected[0]);
  if (!zone || !w.plan) return null;
  const type = w.plan.types.find(t => t.id === zone.type_id);
  return <section className="zoning-inspector" aria-label="Zone inspector">
    <header><div><span className="eyebrow">Zone inspector</span><h2>{type?.name ?? 'Unknown type'}</h2></div><button className="quiet-icon-button" onClick={() => w.pick(null, false)} aria-label="Close zone inspector"><X size={18}/></button></header>
    <span className="zoning-badge">Proposal · {w.scenario?.name}</span><p className="zoning-zone-area">{areaText(zone.area_m2)}</p>
    <label>Zoning type<select value={zone.type_id} disabled={w.readOnly || w.busy || !!w.sketch.tool} onChange={e => void w.execute('assign', { zone_id: zone.id, type_id: e.target.value })}>{w.plan.types.map(t => <option key={t.id} value={t.id}>{t.code} · {t.name}</option>)}</select></label>
    <h3>Effective rules</h3><p className="zoning-muted">Base proposal type · {type?.uses || 'Uses unknown'}</p>
    <dl>{RULE_FIELDS.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{type?.[key] ?? 'Unknown'}</dd></div>)}</dl>
    <details><summary>Reference & sources</summary><p>Existing: Unknown</p><p>{type?.source || 'Source not available'}</p><p className="zoning-muted">{w.plan.baseline.source}</p><p className="zoning-muted">Type version {type?.version} · Zone revision {zone.revision}</p><p className="zoning-muted">Saved {new Date(w.plan.updated_at).toLocaleString()}</p></details>
    <footer><button disabled={w.readOnly || w.busy} onClick={() => w.begin('reshape')}>Edit vertices</button><button disabled={w.readOnly || w.busy} onClick={() => setDeleting(true)}>Delete zone</button></footer>
    {deleting && <ActionDialog title="Delete zone?" message="This removes the selected proposal boundary. You can undo this geometry edit." busy={w.busy} error={w.error} onClose={() => setDeleting(false)} onConfirm={async () => !!await w.execute('delete_zone', { zone_id: zone.id, confirm: true })}/>}
  </section>;
}
