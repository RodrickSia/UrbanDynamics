import { useEffect, useState } from 'react';
import { zoningRequest } from './api';
import { areaText } from './geometry';
import type { Indicators } from './types';
import type { ZoningWorkspace } from './useZoning';
import { DevelopmentComparison } from './DevelopmentComparison';

export function IndicatorsPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const [compareId, setCompareId] = useState('');
  const [result, setResult] = useState<{ key: string; data?: Indicators; error?: string } | null>(null);
  const plan = w.plan, scenario = w.scenario;
  const comparison = plan?.scenarios.find(s => s.id === compareId) ?? plan?.scenarios[0];
  const key = `${plan?.id}/${plan?.revision}/${scenario?.id}/${comparison?.id}`;
  useEffect(() => {
    if (!plan || !scenario || !comparison) return;
    const controller = new AbortController();
    void zoningRequest<Indicators>(`/${plan.id}/indicators?scenario_id=${scenario.id}&compare_id=${comparison.id}`, undefined, controller.signal)
      .then(data => { if (!controller.signal.aborted) setResult({ key, data }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ key, error: error.message }); });
    return () => controller.abort();
  }, [plan, scenario, comparison, key]);
  if (!plan || !scenario) return <div className="zoning-empty"><h3>Choose a plan</h3><p>Open a plan to compare zoning areas and inspect its findings.</p><button onClick={() => w.setPanel('plans')}>Open Plans</button></div>;
  const data = result?.key === key ? result.data : null;
  return <>
    <DevelopmentComparison plan={plan} scenario={scenario}/>
    <label>Compare with<select value={comparison?.id} onChange={e => setCompareId(e.target.value)}>{plan.scenarios.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    {!result || result.key !== key ? <p role="status">Calculating indicators…</p> : result.error ? <p role="alert">{result.error}</p> : null}
    {data && <>
      <div className="zoning-metrics">{[['Assigned', data.assigned_m2], ['Unassigned', data.unassigned_m2], ['Changed', data.changed_m2]] .map(([label, value]) => <div key={label}><span>{label}</span><strong>{areaText(Number(value))}</strong></div>)}</div>
      <p className="zoning-muted">Compared with {comparison?.name} · {data.comparison_status}</p>
      <h3>Zone distribution</h3>
      <div className="zoning-table-scroll"><table><thead><tr><th>Type</th><th>Area</th><th>Change</th></tr></thead><tbody>{data.rows.map(row => <tr key={row.type_id}><th>{plan.types.find(t => t.id === row.type_id)?.code ?? 'Unknown'}</th><td>{areaText(row.area_m2)}</td><td>{row.delta_m2 > 0 ? '+' : ''}{areaText(row.delta_m2)}</td></tr>)}</tbody></table></div>
      {!data.rows.length && <p className="zoning-muted">Draw a zone to start measuring your proposal.</p>}
      <details><summary>Development bounds</summary><p className="zoning-muted">{data.area_basis}. Setbacks, heights and other controls may reduce capacity.</p>{data.rows.map(row => <div className="zoning-bound" key={row.type_id}><strong>{plan.types.find(t => t.id === row.type_id)?.code}</strong><span>FAR bound: {areaText(row.far_bound_m2)}</span><span>Footprint bound: {areaText(row.footprint_bound_m2)}</span></div>)}</details>
      <h3>Validation <span className="zoning-count">{data.findings.length}</span></h3>
      <ul className="zoning-findings">{data.findings.map(f => <li key={f.id}><button onClick={() => {
        const zone = scenario.zones.find(z => z.id === f.zone_id);
        if (zone) { w.pick(zone.id, false); w.zoomTo(zone.geometry); }
        else w.zoomTo(f.geometry ?? plan.study_area);
      }}><span className="zoning-badge">{f.certainty}</span><span>{f.message}</span></button></li>)}</ul>
    </>}
  </>;
}
