import { areaText } from './geometry';
import type { DevelopmentReport } from './developmentTypes';

const labels: Record<string, string> = { max_height: 'Height', max_floors: 'Floors', far: 'FAR', coverage: 'Coverage', setbacks: 'Setbacks', allowed_uses: 'Use' };
export function DevelopmentValues({ report }: { report: DevelopmentReport }) {
  return <>
    <div className="zoning-metrics"><div><span>Proposed GFA</span><strong>{areaText(report.metrics.gfa_m2)}</strong></div>
      <div><span>FAR · Coverage</span><strong>{report.metrics.far.toFixed(2)} · {report.metrics.coverage_pct.toFixed(1)}%</strong></div></div>
    <details open><summary>Built / limits</summary>
      <p className="zoning-muted">Official limits: Unknown. Proposed limits are assumptions.</p>
      <div className="zoning-table-scroll"><table><thead><tr><th>Rule</th><th>Built</th><th>Proposed</th></tr></thead><tbody>
        {report.checks.map(row => <tr key={row.rule}><th>{labels[row.rule] ?? row.rule}</th>
          <td>{row.actual === null ? '—' : `${row.actual.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${row.unit}`}</td>
          <td><span className={row.assumption_status === 'FAIL' ? 'development-fail' : ''}>{row.assumed_limit === null ? 'Unknown' : `${row.assumed_limit} ${row.unit} · ${row.assumption_status}`}</span></td></tr>)}
      </tbody></table></div>
    </details>
  </>;
}
