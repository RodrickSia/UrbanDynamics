import { areaText } from './geometry';
import { RULE_FIELDS } from './types';
import { isZoningCode, ruleGuidance, RULE_SOURCE } from './zoningRules';
import type { ZoningWorkspace } from './useZoning';

export function DevelopmentPanel({ workspace: w }: { workspace: ZoningWorkspace }) {
  const plan = w.plan, scenario = w.scenario, type = w.chosenType;
  if (!plan || !scenario) return null;
  if (!type) return <p className="zoning-muted">Add a zoning type to explore development rules.</p>;
  const area = scenario.zones.filter(z => z.type_id === type.id).reduce((sum, z) => sum + z.area_m2, 0);
  const guidance = ruleGuidance(type.code);
  return <>
    <label>Zoning type<select value={type.id} onChange={e => w.setTypeId(e.target.value)}>{plan.types.map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
    <p className="zoning-muted">{areaText(area)} · proposed area</p>
    <dl className="zoning-development-rules">{RULE_FIELDS.map(([key, label], index) => <div key={key}>
      <dt>{label}</dt><dd><strong>{type[key] ?? (guidance[index].hint.state === 'not_applicable' ? 'N/A' : 'Unknown')}</strong>
        <small>{type[key] !== null ? 'Proposed' : guidance[index].hint.text}</small></dd>
    </div>)}</dl>
    <details><summary>Rule basis</summary><p>{isZoningCode(type.code) ? RULE_SOURCE : 'This land-use code does not establish zoning controls.'}</p><p>{type.source || 'No source attached.'}</p></details>
  </>;
}
