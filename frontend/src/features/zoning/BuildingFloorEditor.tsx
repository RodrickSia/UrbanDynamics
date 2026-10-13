import { useState } from 'react';
import type { BuildingFloor, BuildingInput, ParcelDevelopment } from './developmentTypes';

export function BuildingFloorEditor({ draft, catalog, onChange }: {
  draft: BuildingInput; catalog?: ParcelDevelopment['catalog']; onChange: (patch: Partial<BuildingInput>) => void;
}) {
  const [selection, setSelection] = useState(1);
  const count = Number.isInteger(draft.floors) && draft.floors > 0 && draft.floors <= 200 ? draft.floors : 0;
  const floor = Math.min(selection, count);
  const overrides = draft.floor_overrides ?? [];
  const custom = overrides.find(item => item.floor === floor);
  const value: BuildingFloor = custom ?? { floor, floor_height: draft.floor_height, space_use_id: draft.space_use_id,
    counts_gfa: draft.counts_gfa, counts_far: draft.counts_far };
  const update = (patch: Partial<BuildingFloor>) => onChange({ floor_overrides: [
    ...overrides.filter(item => item.floor !== floor), { ...value, ...patch },
  ].sort((a, b) => a.floor - b.floor) });
  return <details className="development-floor-editor" open>
    <summary>Floor uses <span className="zoning-count">{overrides.length ? `· ${overrides.length} custom` : ''}</span></summary>
    {count > 0 && <>
      <label>Edit floor<select value={floor} onChange={e => setSelection(Number(e.target.value))}>
        {Array.from({ length: count }, (_, i) => <option key={i} value={i + 1}>Floor {i + 1}{overrides.some(o => o.floor === i + 1) ? ' · Custom' : ''}</option>)}
      </select></label>
      <div className="development-fields">
        <label>Floor use<select value={value.space_use_id} onChange={e => update({ space_use_id: e.target.value })}>
          {catalog?.space_uses.map(use => <option key={use.id} value={use.id}>{use.name}</option>)}
        </select></label>
        <label>Floor height (m)<input type="number" min="0.1" max="20" step="any" required value={value.floor_height}
          onChange={e => update({ floor_height: e.target.valueAsNumber })}/></label>
      </div>
      <div className="development-actions">
        <label className="zoning-checkbox"><input type="checkbox" checked={value.counts_gfa} onChange={e => update({ counts_gfa: e.target.checked })}/>GFA</label>
        <label className="zoning-checkbox"><input type="checkbox" checked={value.counts_far} onChange={e => update({ counts_far: e.target.checked })}/>FAR</label>
        <button type="button" disabled={!custom} onClick={() => onChange({ floor_overrides: overrides.filter(item => item.floor !== floor) })}>Reset floor</button>
      </div>
    </>}
  </details>;
}
