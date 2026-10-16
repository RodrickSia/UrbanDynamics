import { useEffect, useState } from 'react';
import { Check, Pentagon, RotateCcw, X, Layers, SlidersHorizontal, ChartColumnIncreasing } from 'lucide-react';
import { API_BASE_URL } from '../../services/api';
import { AreaIndicatorResults } from './AreaIndicatorResults';
import { indicatorDefaults, indicatorFields, type AreaIndicators, type IndicatorAssumptions } from './areaIndicatorTypes';
import { ZoningReport } from './ZoningReport';
import type { ZoningWorkspace } from './useZoning';
import { chartMetrics, chartRows, chartValue, type ChartMetric } from './indicatorChart';

export function IndicatorsPanel({ workspace: w, dashboard = false }: { workspace: ZoningWorkspace; dashboard?: boolean }) {
  const [assumptions, setAssumptions] = useState({ ...indicatorDefaults });
  const [draft, setDraft] = useState({ ...indicatorDefaults });
  const [retry, setRetry] = useState(0);
  const [showPlanReport, setShowPlanReport] = useState(false);
  const [metric, setMetric] = useState<ChartMetric>('population');
  const [showChart, setShowChart] = useState(false);
  const [result, setResult] = useState<{ key: string; data?: AreaIndicators; error?: string }>();
  const drawing = w.sketch.tool === 'analysis';
  const boundPlan = w.indicatorPlan;
  const boundScenario = w.indicatorScenario;
  const key = JSON.stringify({ geometry: w.analysisArea,
    ...(boundPlan && boundScenario ? { plan_id: boundPlan.id, revision: boundPlan.revision, scenario_id: boundScenario.id } : {}),
    include_scenario: !!boundPlan && w.includeScenario, assumptions });
  useEffect(() => {
    if (!JSON.parse(key).geometry || drawing) return;
    const controller = new AbortController();
    const calculate = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/indicators/area`, { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: key,
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(35000)]) });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the selected area and assumptions.');
        if (!controller.signal.aborted) setResult({ key, data });
      } catch (cause) {
        if (!controller.signal.aborted) setResult({ key, error: cause instanceof Error ? cause.message : 'Indicators unavailable' });
      }
    };
    void calculate();
    return () => controller.abort();
  }, [key, drawing, retry]);
  const data = result?.key === key ? result.data : undefined;
  const error = result?.key === key ? result.error : undefined;
  const { setIndicatorChart, indicatorScope } = w;
  useEffect(() => {
    setIndicatorChart(data && !drawing && showChart ? {
      scope: indicatorScope, geometry: data.geometry, metric, rows: chartRows(data, metric),
    } : null);
    return () => setIndicatorChart(null);
  }, [data, drawing, showChart, metric, setIndicatorChart, indicatorScope]);
  const change = (field: keyof IndicatorAssumptions, value: number) => setDraft(previous => ({ ...previous, [field]: value }));
  const assumptionsControl = <details className="indicator-assumptions"><summary aria-label="Assumptions" title="Assumptions">{dashboard ? <SlidersHorizontal size={18}/> : 'Assumptions'}</summary><form onSubmit={event => { event.preventDefault(); setAssumptions({ ...draft }); }}>
    <p className="zoning-muted">Illustrative defaults · adjust to local data</p>
    {indicatorFields.map(([field,label,,min,max]) => <label key={field}>{label}<input type="number" required min={min} max={max}
      step={field === 'transit_radius_m' ? 1 : 'any'} value={Number.isFinite(draft[field]) ? draft[field] : ''} onChange={event => change(field,event.target.valueAsNumber)}/></label>)}
    <button className="zoning-primary" type="submit">Apply assumptions</button>
  </form></details>;
  return <section className="area-indicators" aria-label="Selected area indicators">
    {!dashboard && <div className="indicator-area-actions">
      <button disabled={w.busy || drawing} onClick={() => w.begin('analysis')}><Pentagon size={16}/>Draw area</button>
      {boundPlan && <button disabled={w.busy || drawing} onClick={w.useStudyArea}><RotateCcw size={15}/>Study area</button>}
    </div>}
    {drawing ? <div className="indicator-draw-state"><p>Click to draw · Enter to finish · Ctrl pauses snapping</p><small>{w.sketch.points.length} points</small>
      <div className="zoning-row"><button aria-label="Cancel analysis area" onClick={w.cancel}><X size={16}/>Cancel</button>
        <button className="zoning-primary" disabled={w.sketch.points.length < 3} onClick={() => void w.finish()}><Check size={16}/>Analyze area</button></div>
    </div> : !w.analysisArea && <p className="zoning-muted">Draw a region or choose a plan to start.</p>}
    {!boundPlan && <label>Plan<select value="" disabled={w.loading || w.busy} onChange={event => { if (event.target.value) void w.openPlan(event.target.value); }}>
      <option value="">Select a plan (optional)</option>{w.plans.map(plan => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label>}
    {boundPlan && !dashboard && <p className="indicator-bound-plan">{boundPlan.name} · {boundScenario?.name}</p>}
    <div className={`indicator-toolbar${dashboard ? ' indicator-toolbar-dashboard' : ''}`} role="group" aria-label="Indicator controls">
      {boundPlan && (dashboard ? <button className="quiet-icon-button" title="Include plan scenario" aria-label="Include plan scenario"
        aria-pressed={w.includeScenario} disabled={w.busy} onClick={() => w.setIncludeScenario(!w.includeScenario)}><Layers size={18}/></button>
        : <label className="zoning-check"><input type="checkbox" checked={w.includeScenario}
          disabled={drawing || w.busy} onChange={event => w.setIncludeScenario(event.target.checked)}/>Include plan scenario</label>)}
      {assumptionsControl}
      {dashboard && <button className="quiet-icon-button indicator-chart-toggle" title="3D chart" aria-label="3D chart"
        aria-pressed={showChart} disabled={drawing || !w.analysisArea} onClick={() => setShowChart(value => !value)}><ChartColumnIncreasing size={18}/></button>}
    </div>
    {!drawing && w.analysisArea && <>
      {data && <section className="indicator-chart-controls" aria-label="Map chart">
        {!dashboard && <button className="indicator-chart-toggle" title="3D chart" aria-label="3D chart"
          aria-pressed={showChart} onClick={() => setShowChart(value => !value)}><ChartColumnIncreasing size={17}/></button>}
        <label>Chart metric<select value={metric} onChange={event => setMetric(event.target.value as ChartMetric)}>
          {chartMetrics.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
        {showChart && <>{!chartRows(data, metric).length && <p className="zoning-muted">No data</p>}<ul className="indicator-chart-legend">{chartRows(data, metric).map((row, index) => <li key={index}>
          <span className="zoning-swatch" style={{ backgroundColor: row.value !== null && row.value < 0 ? '#b54e44' : row.color }}/><span>{row.label}</span><strong>{chartValue(row)}</strong></li>)}</ul>
          <small className="zoning-muted">Area totals · relative column heights{metric === 'jobs_balance' ? ' · − = deficit' : ''}</small></>}
      </section>}
      {error ? <div role="alert" className="zoning-error"><p>{error}</p><button onClick={() => setRetry(value => value+1)}>Retry</button></div>
        : data ? <AreaIndicatorResults data={data}/> : <div className="indicator-loading" role="status" aria-busy="true">Calculating selected area…</div>}
    </>}
    {w.plan && !drawing && <details className="indicator-plan-report" onToggle={event => setShowPlanReport(event.currentTarget.open)}>
      <summary>Plan comparison & validation</summary>{showPlanReport && <ZoningReport workspace={w}/>}</details>}
  </section>;
}
