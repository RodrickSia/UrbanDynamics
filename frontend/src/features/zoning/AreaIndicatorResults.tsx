import { indicatorMetrics, type AreaIndicators, type AreaShare } from './areaIndicatorTypes';
import { areaText } from './geometry';

const value = (number: number | null | undefined, digits = 1) => number == null ? 'No data' : number.toLocaleString(undefined, { maximumFractionDigits: digits });
function Distribution({ title, rows }: { title: string; rows: AreaShare[] | null }) {
  return <section className="indicator-distribution" aria-label={title}><h3>{title}</h3>
    {rows === null ? <p className="zoning-muted">No parcel data available.</p> : <>
      <div className="indicator-share-bar" aria-hidden="true">{rows.map((row, index) =>
        <span key={index} style={{ width: `${row.percent}%`, backgroundColor: row.color }}/>)}</div>
      <ul>{rows.map((row, index) => <li key={index}><span className="zoning-swatch" style={{ backgroundColor: row.color }}/>
        <span>{row.code && !['conflict','unmapped'].includes(row.code) ? `${row.code} · ` : ''}{row.label}</span>
        <strong>{value(row.percent)}%</strong></li>)}</ul>
      <small>Share of selected area</small>
    </>}
  </section>;
}

export function AreaIndicatorResults({ data }: { data: AreaIndicators }) {
  const { baseline, proposal, population_source: population, transit, existing_buildings: buildings } = data;
  return <div className="area-indicator-results" aria-label="Area analytics results">
    <p className="zoning-muted">{areaText(data.area_m2)} · {population.year ? `WorldPop ${population.year}` : 'Population unavailable'}</p>
    {population.status === 'partial' && <p role="status" className="zoning-muted">Population coverage {value(population.coverage_percent)}%. Total unavailable.</p>}
    <div className="zoning-table-scroll"><table className="indicator-metric-table"><caption>Estimated capacity & demand</caption>
      <thead><tr><th>Indicator</th><th>Existing</th>{proposal && <th>Proposed</th>}</tr></thead><tbody>
        {indicatorMetrics.map(([key,label,unit]) => <tr key={key}><th scope="row">{label}<small>{unit}</small></th>
          <td>{value(baseline[key])}</td>{proposal && <td>{value(proposal[key])}</td>}</tr>)}
      </tbody></table></div>
    <details className="indicator-methods"><summary>Existing data coverage</summary>
      <p className="zoning-muted" role="note">{!buildings
        ? 'This API version does not provide existing building capacity. Update the backend to use the residential building model.'
        : buildings.status === 'unavailable'
          ? 'Residential building data was unavailable for this area. Housing capacity is unknown.'
          : buildings.status === 'partial'
            ? 'Some residential buildings have missing floor counts. Housing capacity is unknown.'
            : `Housing estimate: ${value(buildings.count, 0)} modeled residential buildings · ${value(buildings.floor_area_m2)} m² floor area. Model coverage is unknown.`}</p>
      <p className="zoning-muted" role="note">Existing jobs need commercial/office floor area and use data. The connected building inventory supplies residential models only.</p>
    </details>
    <p className="zoning-muted">Existing loads: residents only.{proposal ? ' Proposed: saved buildings only, not net change.' : ''}</p>
    <details className="indicator-methods"><summary>How estimates work</summary><ul>
      <li>Population capacity = net residential floor area ÷ m²/person.</li>
      <li>Homes = net residential floor area ÷ m²/home.</li>
      <li>Jobs needed = population × labour force %. Jobs capacity = net workplace floor area ÷ m²/job.</li>
      <li>Jobs balance = capacity − needed. Positive means more proposed jobs than resident demand.</li>
      <li>Residential loads = population × per-person rate. Workplace loads = physical floor area or workers × rate.</li>
      {data.notes.map(note => <li key={note}>{note}</li>)}
    </ul></details>
    <Distribution title="Current land use" rows={data.land_use}/>
    {!!data.zoning.length && <Distribution title="Proposed zoning" rows={data.zoning}/>}
    <section aria-label="Transit accessibility"><h3>Transit accessibility</h3><div className="indicator-transit-value">
      <strong>{value(transit.coverage_percent)}{transit.coverage_percent !== null ? '%' : ''}</strong>
      <span className="zoning-muted">{transit.status === 'missing' ? 'No stop dataset loaded' : `Area within ${transit.radius_m} m · ${transit.stop_count} mapped stops`}</span>
    </div><p className="zoning-muted">Straight-line proximity. Walking routes and service frequency are not measured.</p>
      {transit.status === 'partial' && <p className="zoning-muted">Stop snapshot does not cover the full search area.</p>}
      {transit.source && <details><summary>Transit source</summary><p className="zoning-muted">{transit.source}</p>
        {transit.source.includes('OpenStreetMap') && <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap · ODbL</a>}
        <small>{transit.captured_at?.slice(0,10)} · mapped stops may be incomplete</small></details>}
    </section>
    {!!data.issues.length && <p role="status" className="zoning-muted">{data.issues.join(' · ')}</p>}
  </div>;
}
