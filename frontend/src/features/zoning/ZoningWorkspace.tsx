import { useRef, useState, type CSSProperties } from 'react';
import { Building2, ChartPie, Clapperboard, Copy, Info, LockKeyhole, MoreHorizontal, Pentagon, Plus, UnlockKeyhole, X } from 'lucide-react';
import { MotionIconButton } from '../map/components/MotionIconButton';
import { gsap, motionDuration, useGSAP } from '../map/motion';
import { ActionDialog, ZoningDialog } from './Dialog';
import { ScenarioDialog } from './ScenarioDialog';
import { DevelopmentPanel } from './DevelopmentPanel';
import { IndicatorsPanel } from './IndicatorsPanel';
import { PlanInfoPanel } from './PlanInfoPanel';
import { PlansPanel } from './PlansPanel';
import { PlanZoningPanel } from './PlanZoningPanel';
import { ZoningToolbar } from './ZoningToolbar';
import type { ZoningWorkspace as Workspace } from './useZoning';
import './zoning.css';

const tabs = [
  { id: 'info', label: 'Plan info', icon: Info },
  { id: 'zoning', label: 'Zoning', icon: Pentagon },
  { id: 'development', label: 'Development', icon: Building2 },
  { id: 'dashboard', label: 'Dashboard', icon: ChartPie },
] as const;

export function ZoningWorkspace({ workspace: w, onActivate, searchOpen, searchPanelHeight, onView }: {
  workspace: Workspace; onActivate: () => void; searchOpen: boolean; searchPanelHeight: number; onView?: (mode: '2d' | '3d') => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [dialog, setDialog] = useState<'add_scenario' | 'rename_scenario' | 'delete_scenario' | null>(null);
  const [menu, setMenu] = useState(false);
  const displayedTab = w.selected.length ? 'zoning' : w.section;
  useGSAP(() => {
    if (!w.panel || searchOpen) return;
    if (!w.plan) gsap.fromTo('.zoning-plan-drawer', { opacity: 0, x: -24 },
      { opacity: 1, x: 0, duration: motionDuration(.32), ease: 'power3.out', clearProps: 'transform,opacity' });
    if (w.plan) gsap.fromTo('.zoning-detail-drawer', { opacity: 0, x: 24 },
      { opacity: 1, x: 0, duration: motionDuration(.32), ease: 'power3.out', clearProps: 'transform,opacity' });
  }, { scope: ref, dependencies: [w.panel, w.plan?.id, searchOpen], revertOnUpdate: true });
  return <div ref={ref} className="zoning-workspace" data-has-plan={!!w.plan}>
    <nav className="zoning-nav glass-surface" aria-label="Planning workspace"
      data-search-open={searchOpen} style={{ '--search-panel-height': `${searchPanelHeight}px` } as CSSProperties}>
      <MotionIconButton className="zoning-nav-button" title="Plans" aria-label="Plans" aria-pressed={w.panel === 'plans'} disabled={w.busy} onClick={() => { if (w.panel === 'plans' && !w.plan) w.close(); else { w.back(() => { onActivate(); w.setPanel('plans'); }); } }}><Clapperboard aria-hidden="true" size={19}/></MotionIconButton>
      <MotionIconButton className="zoning-nav-button" title="Indicators" aria-label="Indicators" aria-pressed={w.panel === 'indicators'} disabled={w.busy} onClick={() => { if (w.panel === 'indicators') w.close(); else { w.setSection('dashboard', () => { onActivate(); w.setPanel('indicators'); }); } }}><ChartPie aria-hidden="true" size={19}/></MotionIconButton>
    </nav>
    {w.panel && !searchOpen && <>
      {!w.plan && <aside className="zoning-plan-drawer solid-panel zoning-ui" data-creating={w.sketch.tool === 'study'} aria-label={w.panel === 'indicators' ? 'Indicators panel' : 'Plans panel'}>
        <header><div><h2>{w.panel === 'indicators' ? 'Indicators' : 'Plans'}</h2></div>
          <button className="quiet-icon-button" aria-label="Close zoning workspace" disabled={w.busy} onClick={() => w.close()}><X size={18}/></button></header>
        {!w.plan && w.error && <div className="zoning-error" role="alert">{w.error}</div>}
        {w.panel === 'indicators' ? <IndicatorsPanel workspace={w} onView={onView}/> : <PlansPanel workspace={w}/>}
      </aside>}
      {w.plan && <>
        <aside className="zoning-detail-drawer solid-panel zoning-ui" aria-label="Plan details">
          <header><div><span className="eyebrow">{w.scenario?.name ?? 'Plan'}</span><h2>{w.plan.name}</h2></div>
            <button className="quiet-icon-button" aria-label="Close plan" disabled={w.busy} onClick={() => w.back()}><X size={18}/></button></header>
          <nav className="zoning-detail-tabs" aria-label="Plan sections">{tabs.map(item => <button key={item.id}
            title={item.label} aria-label={item.label} aria-current={displayedTab === item.id ? 'page' : undefined}
            onClick={() => { if (w.selected.length) w.pick(null, false); w.setSection(item.id, () => w.setPanel('plans')); }}><item.icon size={19} aria-hidden="true"/></button>)}</nav>
          {w.error && <div className="zoning-error" role="alert"><p>{w.error}</p><button disabled={w.busy} onClick={() => w.leave(() => void w.openPlan(w.plan!.id))}>Reload plan</button></div>}
          <div key={displayedTab} className="zoning-tab-body">
            {displayedTab === 'info' ? <PlanInfoPanel workspace={w}/>
              : displayedTab === 'zoning' ? <PlanZoningPanel workspace={w}/>
              : displayedTab === 'development' ? <DevelopmentPanel workspace={w} onView={onView}/>
              : <IndicatorsPanel workspace={w} dashboard={w.panel !== 'indicators'} onView={onView}/>}
          </div>
          <p role="status" className="zoning-save-status">{w.busy ? 'Working…' : w.development.dirty ? 'Unsaved proposal' : `Saved · revision ${w.plan.revision}`}</p>
        </aside>
        <div className="zoning-scenario-bar solid-panel zoning-ui" aria-label="Plan scenarios">
          <div className="zoning-scenario-tabs" role="group" aria-label="Select scenario">{w.plan.scenarios.map(s => <button key={s.id} disabled={w.busy || (!!w.sketch.tool && !w.development.dirty)} aria-pressed={w.scenario?.id === s.id} onClick={() => { w.selectScenario(s.id); setMenu(false); }}>
            {s.locked && <LockKeyhole size={13}/>}<span>{s.name}</span>
          </button>)}</div>
          <button className="quiet-icon-button" aria-label="Duplicate scenario" title="Duplicate scenario" disabled={w.busy || !!w.sketch.tool} onClick={() => setDialog('add_scenario')}><Plus size={19}/></button>
          <button className="quiet-icon-button" aria-label="Scenario options" disabled={w.busy || !!w.sketch.tool} aria-expanded={menu} onClick={() => setMenu(!menu)}><MoreHorizontal size={19}/></button>
          {menu && <div className="zoning-scenario-menu solid-panel">
            <button onClick={() => { setDialog('add_scenario'); setMenu(false); }}><Copy size={16}/>Duplicate scenario</button>
            <button disabled={w.scenario?.kind === 'reference' || w.readOnly} onClick={() => { setDialog('rename_scenario'); setMenu(false); }}>Rename scenario</button>
            <button disabled={w.scenario?.kind === 'reference' || w.busy} onClick={() => { void w.execute('lock_scenario', { locked: !w.scenario?.locked }); setMenu(false); }}>{w.scenario?.locked ? <UnlockKeyhole size={16}/> : <LockKeyhole size={16}/>} {w.scenario?.locked ? 'Unlock' : 'Lock'} scenario</button>
            <button disabled={w.readOnly || w.busy} onClick={() => { setDialog('delete_scenario'); setMenu(false); }}>Delete scenario</button>
            <button disabled={w.busy || !w.scenario || w.plan.scenarios.findIndex(s => s.id === w.scenario?.id) < 2} onClick={() => {
              const ids = w.plan!.scenarios.map(s => s.id), index = ids.indexOf(w.scenario!.id);
              [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
              void w.execute('reorder_scenarios', { ids }); setMenu(false);
            }}>Move earlier</button>
            <button onClick={() => { w.setSection('dashboard'); setMenu(false); }}>Compare scenarios</button>
          </div>}
        </div>
        {displayedTab === 'zoning' && <ZoningToolbar workspace={w}/>}
      </>}
    </>}
    {dialog && dialog !== 'delete_scenario' && <ScenarioDialog workspace={w} action={dialog} onClose={() => setDialog(null)}/>}
    {dialog === 'delete_scenario' && <ActionDialog title="Delete scenario?" message="This scenario and its proposals will be removed."
      busy={w.busy} error={w.error} onClose={() => setDialog(null)} onConfirm={async () => !!await w.execute('delete_scenario', { confirm: true })}/>}
    {w.leaving && <ZoningDialog title="Unsaved proposal" onClose={() => { if (!w.busy) void w.resolveLeave('cancel'); }}>
      <p>Save this building before leaving?</p>{w.error && <p role="alert">{w.error}</p>}
      <footer><button disabled={w.busy} onClick={() => void w.resolveLeave('cancel')}>Cancel</button>
        <button disabled={w.busy} onClick={() => void w.resolveLeave('discard')}>Discard</button>
        <button className="zoning-primary" disabled={w.busy} onClick={() => void w.resolveLeave('save')}>Save</button></footer>
    </ZoningDialog>}
  </div>;
}
