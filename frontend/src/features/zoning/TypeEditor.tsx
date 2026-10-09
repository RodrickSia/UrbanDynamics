import { useState } from 'react';
import { ZoningDialog } from './Dialog';
import type { TypeInput, ZoneType } from './types';
import { RULE_FIELDS } from './types';
const EMPTY: TypeInput = { code: '', name: '', color: '#55a99a', description: '', uses: '', source: '',
  max_height: null, max_floors: null, coverage: null, far: null, setback_front: null, setback_side: null, setback_rear: null };

export function TypeEditor({ value, shared, busy, error, onClose, onSave }: {
  value?: ZoneType; shared: boolean; busy: boolean; error: string; onClose: () => void;
  onSave: (value: TypeInput, confirmed: boolean) => Promise<boolean>;
}) {
  const [form, setForm] = useState<TypeInput>(() => value ? Object.fromEntries(Object.keys(EMPTY).map(k => [k, value[k as keyof ZoneType]])) as unknown as TypeInput : EMPTY);
  const [confirmed, setConfirmed] = useState(false);
  return <ZoningDialog title={value ? 'Edit zoning type' : 'New zoning type'} onClose={() => { if (!busy) onClose(); }}>
    <form onSubmit={async e => { e.preventDefault(); if (await onSave(form, confirmed)) onClose(); }}>
      <span className="zoning-badge">Proposal</span>
      <div className="zoning-form-grid">
        <label>Code<input autoFocus required maxLength={20} value={form.code} onChange={e => setForm({ ...form, code: e.target.value })}/></label>
        <label>Color<input type="color" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })}/></label>
      </div>
      <label>Name<input required maxLength={120} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label>
      <label>Intended uses<input maxLength={1000} value={form.uses} onChange={e => setForm({ ...form, uses: e.target.value })} placeholder="Unknown when not specified"/></label>
      <div className="zoning-form-grid">{RULE_FIELDS.map(([key, label, max]) => <label key={key}>{label}<input type="number" min={0} max={max} step={key === 'max_floors' ? 1 : .01}
        value={form[key] ?? ''} placeholder="Unknown" onChange={e => setForm({ ...form, [key]: e.target.value === '' ? null : Number(e.target.value) })}/></label>)}</div>
      <label>Description<textarea maxLength={1000} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}/></label>
      <label>Source / design basis<textarea maxLength={2000} value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} placeholder="Document or explanation for this proposed rule"/></label>
      {shared && <label className="zoning-check"><input required type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>Apply this type change to all scenarios using it.</label>}
      {error && <p role="alert">{error}</p>}
      <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button className="zoning-primary" disabled={busy}>{busy ? 'Saving…' : 'Save type'}</button></footer>
    </form>
  </ZoningDialog>;
}
