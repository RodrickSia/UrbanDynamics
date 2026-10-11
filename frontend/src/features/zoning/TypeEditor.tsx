import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { ZoningDialog } from './Dialog';
import catalog from './zoningCatalog.json';
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
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [query, setQuery] = useState('');
  const matches = useMemo(() => catalog.filter(item =>
    `${item.code} ${item.name} ${item.description}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi'))), [query]);
  const choose = (item: typeof catalog[number]) => {
    setForm(current => ({ ...current, code: item.code, name: item.name, description: item.description,
      source: item.category === 'land_use'
        ? 'Vietnam land-use code reference · Circular 08/2024/TT-BTNMT, Appendix II, Section A. Applied here as a draft zoning type; verify against the approved plan.'
        : `UrbanDynamics 2026 reference catalog · ${item.category === 'zoning_type' ? 'proposed zoning type' : 'optional proposed subtype'}${item.land_use_codes ? ` · Related land-use codes: ${item.land_use_codes}` : ''}. Not a statutory land-use code.` }));
    setCatalogOpen(false);
    setQuery('');
  };
  return <ZoningDialog title={value ? 'Edit zoning type' : 'New zoning type'} onClose={() => { if (!busy) onClose(); }}>
    <form onBlur={e => {
      const next = e.relatedTarget as Node | null;
      const field = e.currentTarget.querySelector('.zoning-code-field');
      const list = e.currentTarget.querySelector('.zoning-code-catalog');
      if (catalogOpen && (!next || (!field?.contains(next) && !list?.contains(next)))) setCatalogOpen(false);
    }} onSubmit={async e => { e.preventDefault(); if (await onSave(form, confirmed)) onClose(); }}>
      <span className="zoning-badge">Proposal</span>
      <div className="zoning-form-grid">
        <div className="zoning-code-field"><label htmlFor="zoning-type-code">Code</label>
          <div className="zoning-code-input"><input id="zoning-type-code" required maxLength={20} value={form.code}
            aria-expanded={catalogOpen} aria-controls={catalogOpen ? 'zoning-code-catalog' : undefined} autoComplete="off"
            onFocus={() => { setQuery(''); setCatalogOpen(true); }}
            onChange={e => { setForm({ ...form, code: e.target.value }); setQuery(e.target.value); setCatalogOpen(true); }}
            onKeyDown={e => { if (e.key === 'Escape' && catalogOpen) { e.preventDefault(); e.stopPropagation(); setCatalogOpen(false); } }}/>
            <button type="button" aria-label="Browse zoning codes" aria-expanded={catalogOpen}
              onClick={() => { setQuery(''); setCatalogOpen(open => !open); }}><ChevronDown size={17}/></button></div>
        </div>
        <label>Color<input type="color" value={form.color} onChange={e => setForm({ ...form, color: e.target.value })}/></label>
      </div>
      {catalogOpen && <div id="zoning-code-catalog" className="zoning-code-catalog" role="region" aria-label="Zoning code catalog">
        <div className="zoning-code-catalog-heading"><strong>Code catalog</strong><small>{matches.length} matches</small></div>
        {!matches.length && <p className="zoning-muted">No catalog match. You can enter a custom code.</p>}
        {(['zoning_type', 'zoning_subtype', 'land_use'] as const).map(category => {
          const items = matches.filter(item => item.category === category);
          if (!items.length) return null;
          return <section key={category} aria-label={{ zoning_type: 'Proposed zoning types', zoning_subtype: 'Proposed subtypes', land_use: 'Land-use code reference' }[category]}>
            <h4>{ { zoning_type: 'Proposed zoning types', zoning_subtype: 'Proposed subtypes', land_use: 'Land-use code reference' }[category] }</h4>
            {items.map(item => <button type="button" className="zoning-code-option" key={`${category}-${item.code}`} onClick={() => choose(item)}>
              <span><strong>{item.code}</strong> {item.name}</span><small>{item.description}</small>
            </button>)}
          </section>;
        })}
      </div>}
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
