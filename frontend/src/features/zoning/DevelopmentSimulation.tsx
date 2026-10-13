import { useState } from 'react';
import { Activity, Download, Play, Square } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';
import { usePlanSimulation } from './usePlanSimulation';
import { simulationDefaults, type SimulationSettings } from './simulationTypes';
import type { Plan, Scenario } from './types';

const fields = [
  ['residential_m2_per_person', 'Residential m² / person', 5, 500],
  ['work_m2_per_staff', 'Workplace m² / staff', 5, 500],
  ['visitors_per_100m2_day', 'Visitors / 100 m² / day', 0, 1000],
  ['green_open_percent', 'Green / open space (%)', 0, 100],
  ['rainfall_mm', 'Rainfall (mm)', 0, 300],
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

export function DevelopmentSimulation({ plan, scenario, disabled }: { plan: Plan; scenario: Scenario; disabled: boolean }) {
  const storageKey = `plan-simulation-settings:${plan.id}:${scenario.id}`;
  const [settings, setSettings] = useState<SimulationSettings>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (stored && fields.every(([key, , min, max]) => Number.isFinite(stored[key]) && stored[key] >= min && stored[key] <= max)) return stored;
    } catch { /* Keep defaults if storage is unavailable. */ }
    return { ...simulationDefaults };
  });
  const [mode, setMode] = useState<'screening' | 'native'>('screening');
  const simulation = usePlanSimulation(plan, scenario, settings);
  const { job, result, error, requesting, running } = simulation;
  const state = result?.options.find(option => option.id === 'proposal')?.state;
  const change = (key: keyof SimulationSettings, value: number) => {
    const next = { ...settings, [key]: value }; setSettings(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Optional local preferences. */ }
  };
  return <section className="development-simulation" aria-label="Development simulation">
    <div className="zoning-row"><h3><Activity size={16}/> Simulation</h3><span className="zoning-badge">What-if</span></div>
    <p className="zoning-muted">Saved buildings · {scenario.name}</p>
    <form onSubmit={event => { event.preventDefault(); void simulation.run(mode); }}>
      <fieldset disabled={disabled || requesting || running}>
        <label>Engine<select value={mode} onChange={event => setMode(event.target.value as typeof mode)}>
          <option value="screening">Screening</option><option value="native">SUMO + SWMM</option>
        </select></label>
        <details><summary>Assumptions</summary>
          {fields.map(([key, label, min, max]) => <label key={key}>{label}<input type="number" min={min} max={max}
            step="any" required value={Number.isFinite(settings[key]) ? settings[key] : ''} onChange={event => change(key, event.target.valueAsNumber)}/></label>)}
          <p className="zoning-muted">Occupancy is estimated from floor use. Commercial uses Other coefficients. Physical floors still generate demand when excluded from GFA.</p>
        </details>
        <p className="zoning-muted">{mode === 'screening' ? 'Estimated loads, runoff and shadows.' : 'Synthetic roads and drainage · longer calculation.'} Existing occupancy and infrastructure capacity are unknown.</p>
        <button className="zoning-primary" type="submit"><Play size={15}/>{requesting ? 'Preparing…' : 'Run simulation'}</button>
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
      <h4>Proposed demand</h4>
      <div className="zoning-table-scroll"><table><caption className="zoning-muted">{result.mode} · assumed occupancy and surfaces</caption><tbody>
        {metrics.filter(([key]) => key in state.metrics).map(([key, label, unit]) => <tr key={key}><th scope="row">{label}</th><td>{format(state.metrics[key])} <small>{unit}</small></td></tr>)}
        <tr><th scope="row">Change vs Existing</th><td>Unknown</td></tr><tr><th scope="row">Available capacity</th><td>Unknown</td></tr>
      </tbody></table></div>
      {state.traffic && <details><summary>Model traffic</summary><div className="zoning-table-scroll"><table><thead><tr><th>Hour</th><th>Done</th><th>Unfinished</th><th>Not departed</th></tr></thead><tbody>
        {state.traffic.runs.map((run, index) => <tr key={index}><th>{run.hour_local}:00</th><td>{run.completed_vehicles}</td><td>{run.unfinished_vehicles}</td><td>{run.undeparted_vehicles}</td></tr>)}
      </tbody></table></div></details>}
      <a className="development-result-link" href={`${API_BASE_URL}/api/v1/planning/runs/${result.id}`} target="_blank" rel="noreferrer"><Download size={15}/>Result & sources</a>
    </>}
  </section>;
}
