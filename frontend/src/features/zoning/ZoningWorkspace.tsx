import { useRef, useState, type CSSProperties } from 'react';
import { ArrowLeft, ChartPie, Clapperboard, Copy, LockKeyhole, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Plus, UnlockKeyhole, X } from 'lucide-react';
import { MotionIconButton } from '../map/components/MotionIconButton';
import { gsap, motionDuration, useGSAP } from '../map/motion';
import { ActionDialog } from './Dialog';
import { IndicatorsPanel } from './IndicatorsPanel';
import { PlansPanel } from './PlansPanel';
import { ZoneInspector } from './ZoneInspector';
import { ZoningToolbar } from './ZoningToolbar';
import type { ZoningWorkspace as Workspace } from './useZoning';
import './zoning.css';

export function ZoningWorkspace({ workspace: w, onActivate, searchOpen, searchPanelHeight }: {
  workspace: Workspace; onActivate: () => void; searchOpen: boolean; searchPanelHeight: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [dialog, setDialog] = useState<'add_scenario' | 'rename_scenario' | 'delete_scenario' | 'rename_plan' | null>(null);
  const [menu, setMenu] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  useGSAP(() => {
    if (!w.panel) return;
    gsap.fromTo('.zoning-panel', { opacity: 0, x: -14 }, { opacity: 1, x: 0, duration: motionDuration(.25), ease: 'power2.out', clearProps: 'transform,opacity' });
  }, { scope: ref, dependencies: [w.panel], revertOnUpdate: true });
  return <div ref={ref} className="zoning-workspace">
    <nav className="zoning-nav glass-surface" aria-label="Planning workspace"
      data-search-open={searchOpen} style={{ '--search-panel-height': `${searchPanelHeight}px` } as CSSProperties}>
      <MotionIconButton className="zoning-nav-button" title="Plans" aria-label="Plans" aria-pressed={w.panel === 'plans'} disabled={w.busy} onClick={() => { if (w.panel === 'plans') w.close(); else { onActivate(); setCollapsed(false); w.setPanel('plans'); } }}><Clapperboard aria-hidden="true" size={19}/></MotionIconButton>
      <MotionIconButton className="zoning-nav-button" title="Indicators" aria-label="Indicators" aria-pressed={w.panel === 'indicators'} disabled={w.busy} onClick={() => { if (w.panel === 'indicators') w.close(); else { onActivate(); setCollapsed(false); w.setPanel('indicators'); } }}><ChartPie aria-hidden="true" size={19}/></MotionIconButton>
    </nav>
    {w.panel && !searchOpen && <>
      {collapsed && <button className="zoning-expand glass-surface" aria-label="Expand zoning panel" onClick={() => setCollapsed(false)}><PanelLeftOpen size={20}/></button>}
      <aside hidden={collapsed} className="zoning-panel glass-panel zoning-ui" aria-label={w.panel === 'plans' ? 'Plans panel' : 'Indicators panel'}>
        <header>{w.plan && <button className="quiet-icon-button" aria-label="Back to plans" disabled={w.busy} onClick={() => { w.back(); w.setPanel('plans'); }}><ArrowLeft size={18}/></button>}
          <div><span className="eyebrow">{w.panel === 'plans' ? 'Plans' : 'Indicators'}</span><h2>{w.plan?.name ?? 'Zoning workspace'}</h2></div>
          <button className="quiet-icon-button" aria-label="Collapse zoning panel" title="Collapse panel to draw on the map" onClick={() => setCollapsed(true)}><PanelLeftClose size={18}/></button>
          <button className="quiet-icon-button" aria-label="Close zoning workspace" disabled={w.busy} onClick={w.close}><X size={18}/></button>
        </header>
        {w.error && <div className="zoning-error" role="alert"><p>{w.error}</p>{w.plan && <button disabled={w.busy} onClick={() => void w.openPlan(w.plan!.id)}>Reload saved plan</button>}</div>}
        {w.panel === 'plans' ? <PlansPanel workspace={w}/> : <IndicatorsPanel workspace={w}/>}
        {w.plan && <p role="status" className="zoning-save-status">{w.busy ? 'Saving changes…' : `Saved · revision ${w.plan.revision}`}</p>}
      </aside>
      {w.plan && <>
        <div className="zoning-scenario-bar glass-surface zoning-ui" aria-label="Plan scenarios">
          <div className="zoning-scenario-tabs" role="group" aria-label="Select scenario">{w.plan.scenarios.map(s => <button key={s.id} disabled={w.busy || !!w.sketch.tool} aria-pressed={w.scenario?.id === s.id} onClick={() => w.selectScenario(s.id)}>
            {s.locked && <LockKeyhole size={13}/>}<span>{s.name}</span>
          </button>)}</div>
          <button className="quiet-icon-button" aria-label="Duplicate scenario" title="Duplicate scenario" disabled={w.busy || !!w.sketch.tool} onClick={() => setDialog('add_scenario')}><Plus size={19}/></button>
          <button className="quiet-icon-button" aria-label="Scenario options" disabled={w.busy || !!w.sketch.tool} aria-expanded={menu} onClick={() => setMenu(!menu)}><MoreHorizontal size={19}/></button>
          {menu && <div className="zoning-scenario-menu glass-panel">
            <button onClick={() => { setDialog('add_scenario'); setMenu(false); }}><Copy size={16}/>Duplicate scenario</button>
            <button onClick={() => { setDialog('rename_plan'); setMenu(false); }}>Rename plan</button>
            <button disabled={w.scenario?.kind === 'reference' || w.readOnly} onClick={() => { setDialog('rename_scenario'); setMenu(false); }}>Rename scenario</button>
            <button disabled={w.scenario?.kind === 'reference' || w.busy} onClick={() => { void w.execute('lock_scenario', { locked: !w.scenario?.locked }); setMenu(false); }}>{w.scenario?.locked ? <UnlockKeyhole size={16}/> : <LockKeyhole size={16}/>} {w.scenario?.locked ? 'Unlock' : 'Lock'} scenario</button>
            <button disabled={w.readOnly || w.busy} onClick={() => { setDialog('delete_scenario'); setMenu(false); }}>Delete scenario</button>
          </div>}
        </div>
        <ZoningToolbar workspace={w}/>
        {!w.sketch.tool && w.selected.length > 0 && <ZoneInspector workspace={w}/>}
      </>}
    </>}
    {dialog && <ActionDialog title={{ add_scenario: 'Duplicate scenario', rename_scenario: 'Rename scenario', rename_plan: 'Rename plan', delete_scenario: 'Delete scenario?' }[dialog]}
      initial={dialog === 'delete_scenario' ? undefined : dialog === 'rename_plan' ? w.plan?.name : dialog === 'add_scenario' ? `${w.scenario?.name} copy` : w.scenario?.name}
      message={dialog === 'delete_scenario' ? 'The selected scenario and its geometry history will be removed. Other scenarios and Existing remain available.' : undefined}
      busy={w.busy} error={w.error} onClose={() => setDialog(null)} onConfirm={async name => !!await w.execute(dialog, dialog === 'delete_scenario' ? { confirm: true } : { name })}/>}
  </div>;
}
