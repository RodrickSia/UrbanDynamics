import { useState } from 'react';
import { Save } from 'lucide-react';
import { CostNumber, CostProfileEditor } from './CostProfileEditor';
import { costArea, costMoney, type ConstructionCostReport, type CostSettings, type ExtraName } from './costTypes';

export function CostSettingsEditor({report, onSave, disabled}: {
  report: ConstructionCostReport; onSave: (value: CostSettings) => Promise<boolean>; disabled: boolean;
}) {
  const [draft, setDraft] = useState<CostSettings>(() => structuredClone(report.settings));
  const [scope, setScope] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const profile = scope ? draft.building_overrides[scope] ?? draft.profile : draft.profile;
  const patch = (next: Partial<CostSettings>) => setDraft(previous => ({...previous, ...next}));
  const dirty = JSON.stringify(draft) !== JSON.stringify(report.settings);
  const defaultRate = report.demolition_default_rate ?? 200000;
  return <form className="cost-settings" onSubmit={async e => {
    e.preventDefault(); if (saving) return;
    setSaving(true); setError('');
    try { if (!await onSave(draft)) setError('Budget not saved. Check the plan error and retry.'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to save budget'); }
    finally { setSaving(false); }
  }}>
    <fieldset disabled={disabled || saving}>
      <legend>Budget assumptions</legend>
      <label>Apply construction settings to<select value={scope} onChange={e => setScope(e.target.value)}>
        <option value="">Scenario default</option>{report.buildings.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select></label>
      {scope && <label className="zoning-check"><input type="checkbox" checked={!!draft.building_overrides[scope]} onChange={e => {
        const overrides = {...draft.building_overrides};
        if (e.target.checked) overrides[scope] = structuredClone(draft.profile); else delete overrides[scope];
        patch({building_overrides:overrides});
      }}/>Custom building quote</label>}
      <fieldset disabled={!!scope && !draft.building_overrides[scope]} className="cost-profile-fields">
        <legend className="sr-only">Construction settings</legend>
        <CostProfileEditor value={profile} perBuilding={!!scope} onChange={next => scope
          ? patch({building_overrides:{...draft.building_overrides,[scope]:next}}) : patch({profile:next})}/>
      </fieldset>
      <details><summary>Demolition</summary>
        <p className="zoning-muted">Saved demolition area: {costArea(report.demolition_area_m2 ?? null)} · footprint × floors.</p>
        <label className="zoning-check"><input type="checkbox" checked={draft.demolition_included}
          onChange={e => patch({demolition_included:e.target.checked})}/>Included in construction quote</label>
        <CostNumber label="Demolition (VND/m²)" max={1e9} disabled={draft.demolition_included}
          value={draft.demolition_rate ?? defaultRate} onChange={demolition_rate => patch({demolition_rate})}/>
        <div className="zoning-row"><small className="zoning-muted">{draft.demolition_rate === null ? 'Automatic · app assumption' : 'Custom rate'}</small>
          <button type="button" disabled={draft.demolition_included || draft.demolition_rate === null}
            onClick={() => patch({demolition_rate:null})}>Reset to {costMoney(defaultRate)}/m²</button></div>
        <label>Demolition area<select disabled={draft.demolition_included} value={draft.demolition_area_m2 === null ? 'auto' : 'custom'}
          onChange={e => patch({demolition_area_m2:e.target.value === 'auto' ? null : report.demolition_area_m2 ?? 0})}>
          <option value="auto">Automatic · demolished buildings</option><option value="custom">Custom total floor area</option>
        </select></label>
        {draft.demolition_area_m2 === null
          ? <CostNumber label="Estimated floor height (m)" min={2} max={10} disabled={draft.demolition_included}
              value={draft.demolition_floor_height_m ?? 3.2} onChange={n => patch({demolition_floor_height_m:n!})}/>
          : <CostNumber label="Total demolition floor area (m²)" max={1e8} disabled={draft.demolition_included}
              value={draft.demolition_area_m2} onChange={demolition_area_m2 => patch({demolition_area_m2})}/>}
        <small className="zoning-muted">Recorded floors take priority. Otherwise, floors are estimated from building height. Save to recalculate.</small>
        <label>Demolition source<input required maxLength={1000} value={draft.demolition_source} onChange={e => patch({demolition_source:e.target.value})}/></label>
      </details>
      <details><summary>Extras · once per scenario</summary>
        {(['piling','design','permit','special'] as ExtraName[]).map((name,i) => {
          const extra = draft.extras[name] ?? {amount:0,included:false};
          const update = (next: Partial<typeof extra>) => patch({extras:{...draft.extras,[name]:{...extra,...next}}});
          return <div className="cost-extra" key={name}>
            <CostNumber label={`${['Piling','Design','Permit','Special works'][i]} (VND)`} value={extra.amount}
              disabled={extra.included} onChange={n => update({amount:n!})}/>
            <label className="zoning-check"><input type="checkbox" checked={extra.included} onChange={e => update({included:e.target.checked})}/>Included</label>
          </div>;
        })}
      </details>
      <details><summary>VAT & contingency</summary>
        <label className="zoning-check"><input type="checkbox" checked={draft.vat_included} onChange={e => patch({vat_included:e.target.checked})}/>Quote includes VAT</label>
        <div className="development-fields">
          <CostNumber label="VAT (%)" max={100} disabled={draft.vat_included} value={draft.vat_pct} onChange={n => patch({vat_pct:n!})}/>
          <CostNumber label="Contingency (%)" max={100} value={draft.reserve_pct} onChange={n => patch({reserve_pct:n!})}/>
        </div>
        <small className="zoning-muted">Rates are contract assumptions. Initial VAT and contingency are 0%.</small>
      </details>
      {error && <p role="alert" className="zoning-error">{error}</p>}
      <button type="submit" className="zoning-primary" disabled={!dirty}><Save size={16}/>{saving ? 'Saving…' : 'Save budget'}</button>
    </fieldset>
  </form>;
}
