import { useState } from 'react';
import { Activity, Download, History, Play, Square } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';
import { usePlanSimulation } from './usePlanSimulation';
import { simulationDefaults, type SimulationSettings, type ComparisonRow } from './simulationTypes';
import type { Plan, Scenario } from './types';
import type { FeatureCollection } from 'geojson';

const fields = [
  ['residential_m2_per_person', 'Residential m² / person', 5, 500],
  ['work_m2_per_staff', 'Workplace m² / staff', 5, 500],
  ['visitors_per_100m2_day', 'Visitors / 100 m² / day', 0, 1000],
  ['school_m2_per_student', 'School gross floor m² / student (assumed)', 2, 100],
  ['school_students_per_staff', 'School students / staff (assumed)', 1, 100],
  ['green_open_percent', 'Green / open space (%)', 0, 100],
  ['rainfall_mm', 'Rainfall (mm)', 0, 300],
  ['traffic_radius_m', 'Road context beyond study boundary (m)', 500, 1500],
] as const;
const metrics = [
  ['residents', 'Residents', 'people'], ['floor_area_m2', 'GFA', 'm²'],
  ['freshwater_m3_day', 'Water', 'm³/day'], ['wastewater_m3_day', 'Wastewater', 'm³/day'],
  ['energy_kwh_day', 'Energy', 'kWh/day'], ['power_peak_kw', 'Peak power', 'kW'],
  ['person_trips_day', 'Travel demand', 'trips/day'], ['unretained_runoff_m3', 'Runoff', 'm³/event'],
  ['mean_shaded_receiver_m2', 'Mean shaded area', 'm²'],
  ['node_flooding_m3', 'Model overflow', 'm³/event'], ['runoff_peak_m3_s', 'Peak runoff', 'm³/s'],
] as const;
const format = (value: number | null | undefined) => value == null ? 'Unknown' : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
const trafficMetrics: Record<string, string> = {
  mean_completed_delay_seconds: 'Delay per completed trip', background_completed_delay_seconds: 'Delay for background traffic',
  max_queue_length_m: 'Maximum queue length', completed_vehicles: 'Completed vehicles',
  unfinished_vehicles: 'Unfinished vehicles', undeparted_vehicles: 'Vehicles not departed',
};

export function ComparisonTable({ rows, traffic = false }: {rows: ComparisonRow[]; traffic?: boolean}) {
  return <div className="zoning-table-scroll"><table className="simulation-comparison">
    <thead><tr><th>Indicator</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
    <tbody>{rows.map((row, index) => {
      const values = traffic ? row.scenario_values ?? row : row;
      const incomplete = row.comparability_reason === 'incomplete_trip_bias' || row.comparability === 'not_comparable'
        || (row.metric.endsWith('delay_seconds') && row.trip_population_complete === false);
      return <tr key={`${row.metric}-${row.hour_local}-${row.seed}-${index}`}>
        <th scope="row">{traffic ? trafficMetrics[row.metric] : metrics.find(([key]) => key === row.metric)?.[1] ?? row.metric}
          <small>{row.unit}{row.hour_local != null ? ` · ${row.hour_local}:00 · seed ${row.seed}` : ''}</small>
          <small>{traffic && row.scenario_values ? 'Assumption-based comparison' : row.comparability === 'insufficient_data' ? 'Insufficient data' : incomplete ? 'Not comparable' : 'Scenario estimate'}</small>
        </th><td>{format(values.before)}</td><td>{format(values.after)}</td>
        <td>{incomplete ? 'Not comparable' : format(values.delta)}</td>
      </tr>;
    })}</tbody>
  </table></div>;
}

export function DevelopmentSimulation({ plan, scenario, parcelId, disabled, mapBuildings }: { plan: Plan; scenario: Scenario; parcelId: string | null; disabled: boolean; mapBuildings?: FeatureCollection }) {
  const storageKey = `plan-simulation-settings:${plan.id}:${scenario.id}`;
  const [settings, setSettings] = useState<SimulationSettings>(() => {
    try {
      const stored = { ...simulationDefaults, ...JSON.parse(localStorage.getItem(storageKey) ?? 'null') };
      if (stored && fields.filter(([key]) => key !== 'traffic_radius_m').every(([key, , min, max]) => Number.isFinite(stored[key]) && stored[key] >= min && stored[key] <= max)) {
        return { ...simulationDefaults, ...Object.fromEntries(fields.filter(([key, , min, max]) => Number.isFinite(stored[key]) && stored[key] >= min && stored[key] <= max).map(([key]) => [key, stored[key]])),
          landscape_mode: stored.landscape_mode === 'redesign' ? 'redesign' : 'preserve' };
      }
    } catch { /* Keep defaults if storage is unavailable. */ }
    return { ...simulationDefaults };
  });
  const [mode, setMode] = useState<'screening' | 'native'>('screening');
  const [scope, setScope] = useState<'parcel' | 'scenario'>('parcel');
  const simulation = usePlanSimulation(plan, scenario, settings, scope === 'parcel' ? parcelId : null, scope === 'scenario' || !!parcelId, scope === 'parcel' ? mapBuildings : undefined);
  const { job, result, error, requesting, running } = simulation;
  const option = result?.options.find(option => option.id === 'proposal');
  const state = option?.state;
  const trafficRows = option?.traffic_comparison ?? [];
  const impactRows = [...(option?.comparison ?? []), ...(option?.drainage_comparison ?? [])];
  const sources = result?.context?.development_context;
  const change = <K extends keyof SimulationSettings>(key: K, value: SimulationSettings[K]) => {
    const next = { ...settings, [key]: value }; setSettings(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Optional local preferences. */ }
  };
  return <section className="development-simulation" aria-label="Development simulation">
    <div className="zoning-row"><h3><Activity size={16}/> Simulation</h3><span className="zoning-badge">What-if</span></div>
    <p className="zoning-muted">{scope === 'parcel' && parcelId ? parcelId.startsWith('zone:') ? 'Selected zoning' : `Parcel ${parcelId}` : scenario.name}</p>
    <form onSubmit={event => { event.preventDefault(); void simulation.run(mode); }}>
      <fieldset disabled={disabled || requesting || running}>
        <label>Scope<select value={scope} onChange={event => setScope(event.target.value as typeof scope)}>
          <option value="parcel">{parcelId?.startsWith('zone:') ? 'Selected zoning' : 'Selected parcel'}</option><option value="scenario">Whole scenario</option>
        </select></label>
        <label>Engine<select value={mode} onChange={event => setMode(event.target.value as typeof mode)}>
          <option value="screening">Quick estimate</option><option value="native">Detailed · SUMO + SWMM</option>
        </select></label>
        <details><summary>Assumptions</summary>
          <label>Landscape<select value={settings.landscape_mode} onChange={event => change('landscape_mode', event.target.value as SimulationSettings['landscape_mode'])}>
            <option value="preserve">Keep existing landscape outside buildings</option>
            <option value="redesign">Redesign all open ground in this scope</option>
          </select></label>
          {fields.filter(([key]) => key !== 'green_open_percent' || settings.landscape_mode === 'redesign').map(([key, label, min, max]) => <label key={key}>{label}<input type="number" min={min} max={max}
            step="any" required value={Number.isFinite(settings[key]) ? settings[key] : ''} onChange={event => change(key, event.target.valueAsNumber)}/></label>)}
          <p className="zoning-muted">Occupancy follows floor use; physical floors still count when excluded from GFA. Ground cover is kept unless the design changes it. Missing ground cover and traffic counts use assumptions.</p>
        </details>
        <div className="simulation-actions">
          <button className="zoning-primary simulation-run" type="submit" disabled={scope === 'parcel' && !parcelId}><Play size={15}/>{requesting ? 'Preparing…' : 'Run simulation'}</button>
          <button className="simulation-history" type="button" disabled={requesting || running || disabled || (scope === 'parcel' && !parcelId)} onClick={() => void simulation.loadSaved()}><History size={16}/>View last completed run</button>
        </div>
        {scope === 'parcel' && !parcelId && <small className="simulation-hint">Select a parcel to run.</small>}
      </fieldset>
    </form>
    {disabled && <p className="zoning-muted">Save or discard the draft before running.</p>}
    {job && <div role="status" className="development-simulation-status">
      {job.cancel_requested && running ? 'Cancellation requested' : job.status === 'queued' ? 'Queued · waiting for simulation worker' : job.status}
      {running && job.progress?.module && <small>{job.progress.module} {job.progress.done ?? ''}{job.progress.total ? ` / ${job.progress.total}` : ''}</small>}
      {simulation.study && mode === 'native' && <small>{simulation.study.native_work_estimate.sumo_runs} SUMO · {simulation.study.native_work_estimate.swmm_runs} SWMM runs</small>}
    </div>}
    {running && <button disabled={requesting || job?.cancel_requested} onClick={() => void simulation.action('cancel')}><Square size={14}/>Cancel simulation</button>}
    {job && ['failed', 'partial', 'cancelled'].includes(job.status) && <button disabled={requesting} onClick={() => void simulation.action('retry')}>Retry simulation</button>}
    {(error || job?.error) && <p role="alert">{error || job?.error}</p>}
    {state && result && <>
      <h4>Building impact · before and after</h4>
      <p className="zoning-muted">Saved result: {result.mode === 'native' ? 'Detailed simulation (SUMO + SWMM)' : 'Quick estimate'}. Values use that run's captured inputs. Changing controls requires a new run.</p>
      <p className="zoning-muted">Scenario estimates, not surveyed conditions. Unknown means the available data cannot establish a comparison.</p>
      {option && <ComparisonTable rows={impactRows.filter(row => metrics.some(([key]) => key === row.metric))
        .map(row => ({...row, after: row.after ?? state.metrics[row.metric] ?? null}))}/>}
      {sources?.capacity?.status === 'synthetic' ? <p className="zoning-muted">
        Demo connection limits: water {format(sources.capacity.water_capacity_m3_day)} m³/day · wastewater {format(sources.capacity.wastewater_capacity_m3_day)} m³/day · peak power {format(sources.capacity.power_capacity_kw)} kW.
        {' '}Assumed at 125% of existing building demand, not surveyed network capacity.
      </p> : <p className="zoning-muted">Available infrastructure capacity: Unknown. Demand alone does not establish overload.</p>}
      {trafficRows.length > 0 && <>
        <h4>Traffic · same background, added building trips</h4>
        <p className="zoning-muted">Counts and delays are model outputs under the stated OD assumptions. When trips remain unfinished, completed-trip delay cannot establish an improvement.</p>
        <ComparisonTable traffic rows={trafficRows.filter(row => row.metric in trafficMetrics)}/>
      </>}
      {sources && <details open className="simulation-sources"><summary>Data sources and assumptions</summary>
        <dl>
          <dt>Existing buildings · {sources.inventory?.status ?? 'unknown'}</dt><dd>{sources.inventory?.source}
            {sources.inventory?.building_count != null && <small>{sources.inventory.building_count} existing buildings used for the baseline estimate.</small>}
            {!!sources.inventory?.proposed_school_places && <small>Proposed school: {format(sources.inventory.proposed_school_places)} assumed student places. {sources.inventory.school_note}</small>}</dd>
          <dt>Ground cover · {sources.surfaces?.status ?? 'unknown'}</dt><dd>{sources.surfaces?.note}
            {sources.surfaces && <small>Scope: {sources.surfaces.scope}. Unclassified ground: {format(sources.surfaces.unclassified_surface_m2)} m².
              {sources.surfaces.landcover && ` ${sources.surfaces.landcover.dataset ?? 'Historical landcover'}.`}</small>}</dd>
          <dt>Road network</dt><dd>{sources.traffic?.network === 'osm_local' ? `OSM local extract · ${sources.traffic.radius_m} m buffer · captured ${sources.traffic.captured_at ?? 'unknown'}` : 'Local OSM network is prepared on a detailed run.'}<small>{sources.traffic?.network_source}</small></dd>
          <dt>Background traffic · {sources.traffic?.status ?? 'unknown'}</dt><dd>{format(sources.traffic?.background_vehicles_hour)} vehicles/hour at 18:00. {sources.traffic?.source}<small>{sources.traffic?.note}</small></dd>
          <dt>Infrastructure capacity · {sources.capacity?.status === 'synthetic' ? 'demo assumption' : sources.capacity?.status ?? 'unknown'}</dt><dd>{sources.capacity?.source}</dd>
        </dl>
      </details>}
      {state.vietnam_planning_requirements && <details><summary>Planning references</summary>
        <p className="zoning-muted">Reference screening · site-specific approval unverified</p>
        <ul>{state.vietnam_planning_requirements.density_checks.map(check => <li key={check.project_id}>
          {check.project_id}: {check.status.replaceAll('_',' ')}{check.maximum_percent != null ? ` · ${format(check.maximum_percent)}%` : ''}
        </li>)}</ul>
        <a href={state.vietnam_planning_requirements.source_url} target="_blank" rel="noreferrer">QCVN reference</a>
      </details>}
      <a className="development-result-link" href={`${API_BASE_URL}/api/v1/planning/runs/${result.id}`} target="_blank" rel="noreferrer"><Download size={15}/>Result & sources</a>
    </>}
  </section>;
}
