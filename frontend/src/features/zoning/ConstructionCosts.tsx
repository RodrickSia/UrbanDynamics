import { useEffect, useState } from 'react';
import { Building2, Hammer, SlidersHorizontal } from 'lucide-react';
import { zoningRequest } from './api';
import type { Plan, Scenario } from './types';
import { costArea, costMoney, type ConstructionCostReport, type CostSettings } from './costTypes';
import { CostSettingsEditor } from './CostSettingsEditor';
import './constructionCosts.css';

export function ConstructionCosts({plan, scenario, onSave, busy}: {
  plan: Plan; scenario: Scenario; busy: boolean; onSave: (settings: CostSettings) => Promise<boolean>;
}) {
  const [result, setResult] = useState<{data?: ConstructionCostReport; error?: string}>({});
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    zoningRequest<ConstructionCostReport>(`/${encodeURIComponent(plan.id)}/costs?scenario_id=${encodeURIComponent(scenario.id)}&revision=${plan.revision}`,
      undefined, controller.signal).then(data => { if (!controller.signal.aborted) setResult({data}); })
      .catch(cause => { if (!controller.signal.aborted) setResult({error:cause instanceof Error ? cause.message : 'Costs unavailable'}); });
    return () => controller.abort();
  }, [plan.id, plan.revision, scenario.id, retry]);
  const data = result.data;
  return <section className="construction-costs" aria-label="Construction budget">
    <div className="zoning-row"><h3>Construction budget</h3><span className="zoning-badge">{scenario.name}</span></div>
    {result.error ? <div className="zoning-error" role="alert"><p>{result.error}</p><button onClick={() => {setResult({});setRetry(n => n+1);}}>Retry budget</button></div>
      : !data ? <div className="indicator-loading" role="status" aria-busy="true">Calculating budget…</div> : <>
        <div className="cost-total" aria-live="polite"><span>{data.total === null ? 'Known costs · incomplete' : 'Estimated plan cost'}</span>
          <strong>{costMoney(data.total ?? data.known_total)}</strong><small>Construction + demolition · VND</small></div>
        {scenario.kind === 'reference' && <p className="zoning-muted">Existing buildings are retained. Choose a proposal to estimate construction work.</p>}
        <dl className="cost-breakdown">{([
          ['Construction',data.construction],['Demolition',data.demolition],['Extras',data.extras],['VAT',data.vat],['Contingency',data.reserve],
        ] as const).map(([label,amount]) => <div key={label}><dt>{label}</dt><dd>{costMoney(amount)}</dd></div>)}</dl>
        {data.warnings.length > 0 && <ul className="cost-notes">{data.warnings.map(note => <li key={note}>{note}</li>)}</ul>}
        {data.buildings.length === 0 && scenario.kind !== 'reference' && <p className="zoning-muted">Add buildings in Development to estimate construction.</p>}
        {data.buildings.map(row => <details className="cost-building" key={row.id}>
          <summary><Building2 size={17}/><span>{row.name}</span><strong>{costMoney(row.total)}</strong></summary>
          <div className="cost-building-details"><p>{costArea(row.converted_m2)} × {costMoney(row.unit_price)}/m² × {row.adjustment.toLocaleString('vi-VN')} = <b>{costMoney(row.base)}</b></p>
            <dl className="cost-breakdown">{row.components.map((part,index) => <div key={index}><dt>{part.name}</dt><dd>{costArea(part.area_m2)} × {part.factor}</dd></div>)}</dl>
            <small className="zoning-muted">Building total includes configured VAT and contingency. Shared extras and demolition are counted once above.</small>
            <p className="zoning-muted">{row.source}<br/>{row.area_source}</p></div>
        </details>)}
        {!!data.demolitions.length && <details className="cost-building"><summary><Hammer size={17}/><span>Demolition · {data.demolitions.length}</span><strong>{costMoney(data.demolition)}</strong></summary>
          <div className="cost-building-details">{data.demolitions.map(row => <div className="cost-demolition" key={row.id}>
            <b>{row.name}</b><span>{costArea(row.area_m2)} · {costMoney(row.total)}</span><small>{row.source}</small>
          </div>)}</div></details>}
        <details className="cost-assumptions"><summary><SlidersHorizontal size={16}/>Budget assumptions</summary>
          <CostSettingsEditor report={data} onSave={onSave} disabled={busy || scenario.locked || scenario.kind === 'reference'}/></details>
        <p className="cost-formula">(Construction + extras + demolition) × (1 + VAT) × (1 + contingency)</p>
        <small className="zoning-muted">Indicative construction cost · excludes land purchase. Townhouse presets are user-supplied 2026 references.</small>
      </>}
  </section>;
}
