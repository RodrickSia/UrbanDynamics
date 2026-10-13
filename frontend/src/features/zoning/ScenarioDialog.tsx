import { useState } from 'react';
import { ZoningDialog } from './Dialog';
import type { ZoningWorkspace } from './useZoning';

export function ScenarioDialog({ workspace: w, action, onClose }: {
  workspace: ZoningWorkspace; action: 'add_scenario' | 'rename_scenario'; onClose: () => void;
}) {
  const [name, setName] = useState(action === 'add_scenario' ? `${w.scenario?.name} copy` : w.scenario?.name ?? '');
  const [description, setDescription] = useState(action === 'add_scenario' ? '' : w.scenario?.description ?? '');
  const [source, setSource] = useState(w.scenario?.id ?? '');
  return <ZoningDialog title={action === 'add_scenario' ? 'New scenario' : 'Scenario settings'} onClose={() => { if (!w.busy) onClose(); }}>
    <form onSubmit={async e => { e.preventDefault(); if (await w.execute(action, { name, description }, source)) onClose(); }}>
      <fieldset disabled={w.busy} className="development-fieldset">
        <label>Name<input required maxLength={120} autoFocus value={name} onChange={e => setName(e.target.value)}/></label>
        <label>Description<textarea maxLength={2000} value={description} onChange={e => setDescription(e.target.value)}/></label>
        {action === 'add_scenario' && <label>Based on<select value={source} onChange={e => setSource(e.target.value)}>{w.plan?.scenarios.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
        {w.error && <p role="alert">{w.error}</p>}
        <footer><button type="button" onClick={onClose}>Cancel</button><button className="zoning-primary">Confirm</button></footer>
      </fieldset>
    </form>
  </ZoningDialog>;
}
