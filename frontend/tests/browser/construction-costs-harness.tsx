import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../src/styles.css';
import '../../src/features/zoning/zoning.css';
import { IndicatorsPanel } from '../../src/features/zoning/IndicatorsPanel';
import { zoningRequest } from '../../src/features/zoning/api';
import type { Plan } from '../../src/features/zoning/types';
import type { ZoningWorkspace } from '../../src/features/zoning/useZoning';
import fixture from './cost-fixture.json';

const chart = () => {};
function Harness() {
  const [plan, setPlan] = useState(fixture.plan as unknown as Plan);
  const [dashboard, setDashboard] = useState(true);
  const [busy,setBusy] = useState(false);
  const [scenarioIndex,setScenarioIndex] = useState(1);
  const scenario = plan.scenarios[scenarioIndex];
  const workspace = {
    plan, indicatorPlan:plan, indicatorScenario:scenario, busy, loading:false,
    sketch:{tool:'select',points:[]}, plans:[], analysisArea:plan.study_area,
    includeScenario:true, setIncludeScenario:() => {}, setIndicatorChart:chart, indicatorScope:'test',
    execute:async (action:string, payload:Record<string,unknown>, scenario_id:string) => {
      setBusy(true);
      try {
        const next = await zoningRequest<Plan>(`/${plan.id}/commands`,{revision:plan.revision,scenario_id,action,payload});
        setPlan(next);return next;
      } finally {setBusy(false);}
    },
  } as unknown as ZoningWorkspace;
  return <main className="zoning-ui zoning-detail-drawer" style={{width:'min(440px, 100vw)'}}>
    <h2>Dashboard</h2><div className="zoning-row">
      <button onClick={() => setScenarioIndex(n => 1-n)}>Change scenario</button>
      <button onClick={() => setDashboard(v => !v)}>Switch panel</button>
    </div><IndicatorsPanel workspace={workspace} dashboard={dashboard}/>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
