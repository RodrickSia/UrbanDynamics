import { useState } from 'react';
import type { DevelopmentMetrics } from './developmentTypes';
import type { Plan, Scenario } from './types';

const rows: [keyof DevelopmentMetrics, string, string][] = [
  ['gfa_m2', 'Proposed GFA', 'm²'], ['footprint_m2', 'Footprint', 'm²'], ['far', 'FAR', ''],
  ['coverage_pct', 'Coverage', '%'], ['demolition_m2', 'Demolition', 'm²'], ['buildings', 'Buildings', ''],
];
export function DevelopmentComparison({ plan, scenario }: { plan: Plan; scenario: Scenario }) {
  const [id, setId] = useState('');
  const comparison = plan.scenarios.find(s => s.id === id) ?? plan.scenarios.find(s => s.id !== scenario.id) ?? scenario;
  const a = comparison.development_metrics, b = scenario.development_metrics;
  return <section aria-label="Development comparison"><h3>Development comparison</h3>
    <label>Alternative A<select value={comparison.id} onChange={e => setId(e.target.value)}>{plan.scenarios.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    <p className="zoning-muted">B: {scenario.name} · Δ = B − A</p>
    <div className="zoning-table-scroll"><table><thead><tr><th>Measure</th><th>A</th><th>B</th><th>Δ</th></tr></thead><tbody>
      {rows.map(([key, label, unit]) => {
        const x = a?.[key], y = b?.[key];
        const numeric = typeof x === 'number' && typeof y === 'number';
        const format = (v: number) => `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`;
        return <tr key={key}><th>{label}</th><td>{typeof x === 'number' ? format(x) : 'Unknown'}</td><td>{typeof y === 'number' ? format(y) : 'Unknown'}</td><td>{numeric ? format(y - x) : '—'}</td></tr>;
      })}
    </tbody></table></div>
    <p className="zoning-muted">Proposal-only metrics · same study area. Existing building GFA is unknown. Regulatory compliance is unverified.</p>
    {!!b?.space_use_m2 && <details><summary>Proposed space use</summary><dl className="zoning-development-rules">{Object.entries(b.space_use_m2).map(([use, area]) => <div key={use}><dt>{use}</dt><dd>{area.toLocaleString(undefined, { maximumFractionDigits: 1 })} m²</dd></div>)}</dl></details>}
  </section>;
}
