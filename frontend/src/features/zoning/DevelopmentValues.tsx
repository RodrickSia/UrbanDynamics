import { areaText } from './geometry';
import type { DevelopmentReport, ParcelDevelopment } from './developmentTypes';

const labels: Record<string, string> = { max_height: 'Height', max_floors: 'Floors', far: 'FAR', coverage: 'Coverage', setbacks: 'Min. setback', allowed_uses: 'Use' };
export function DevelopmentValues({ report, baseline, existing = false, scenarioSetback }: { report: DevelopmentReport; baseline?: ParcelDevelopment['baseline']; existing?: boolean; scenarioSetback?: number | null }) {
  const current = baseline?.metrics;
  const currentValue = (rule: string) => current && rule in current ? current[rule as keyof typeof current] : null;
  const format = (value: number | null | undefined) => value == null ? 'No data' : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return <>
    <div className="zoning-metrics"><div><span>Existing GFA · estimated</span><strong>{areaText(current?.gfa_m2 ?? null)}</strong>
      <small>FAR {format(current?.far)} · {format(current?.coverage_pct)}{current ? '%' : ''}</small></div>
      {!existing && <div><span>Proposed GFA</span><strong>{areaText(report.metrics.gfa_m2)}</strong>
        <small>FAR {report.metrics.far.toFixed(2)} · {report.metrics.coverage_pct.toFixed(1)}%</small></div>}</div>
    {baseline?.source && <small>{baseline.source}</small>}
    <details open><summary>Built / limits</summary>
      <p className="zoning-muted">Official limits: Unknown. Proposed limits are assumptions.</p>
      <div className="zoning-table-scroll"><table><thead><tr><th>Rule</th><th>Existing</th>{!existing && <th>Proposed</th>}<th>Limit</th></tr></thead><tbody>
        {report.checks.map(row => <tr key={row.rule}><th>{labels[row.rule] ?? row.rule}</th>
          <td>{format(currentValue(row.rule === 'coverage' ? 'coverage_pct' : row.rule))}{currentValue(row.rule === 'coverage' ? 'coverage_pct' : row.rule) != null ? ` ${row.unit}` : ''}</td>
          {!existing && <td>{format(row.rule === 'setbacks' && scenarioSetback !== undefined ? scenarioSetback : row.actual)} {row.unit}</td>}
          <td><span className={row.assumption_status === 'FAIL' ? 'development-fail' : ''}>{row.assumed_limit === null ? 'Unknown' : `${row.assumed_limit} ${row.unit} · ${row.assumption_status}`}</span></td></tr>)}
      </tbody></table></div>
      <small>Min. setback: footprint to parcel boundary, estimated. Front/rear/side limits require frontage data.</small>
    </details>
  </>;
}
