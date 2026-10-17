import { Plus, Trash2 } from 'lucide-react';
import { costPackages, type CostProfile } from './costTypes';

export function CostNumber({label, value, onChange, optional = false, max = 1e15, min = 0, disabled = false}: {
  label: string; value: number | null; onChange: (n: number | null) => void;
  optional?: boolean; max?: number; min?: number; disabled?: boolean;
}) {
  return <label>{label}<input type="number" min={min} max={max} step="any" disabled={disabled}
    required={!optional} value={value !== null && Number.isFinite(value) ? value : ''}
    placeholder={optional ? 'Automatic / unknown' : undefined}
    onChange={e => onChange(e.target.value === '' && optional ? null : e.target.valueAsNumber)}/></label>;
}

export function CostProfileEditor({value, onChange, perBuilding}: {
  value: CostProfile; onChange: (profile: CostProfile) => void; perBuilding: boolean;
}) {
  const patch = (update: Partial<CostProfile>) => onChange({...value, ...update});
  return <div className="cost-profile-editor">
    <label>Construction package<select value={value.package} onChange={e => {
      const item = costPackages.find(row => row[0] === e.target.value)!;
      patch({package: item[0], unit_price: item[2], rate_source: item[0] === 'custom' || item[0] === 'premium'
        ? 'User project quote' : 'User-supplied HCMC 2026 townhouse reference'});
    }}>{costPackages.map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    <CostNumber label="Unit price (VND/m²)" value={value.unit_price} max={1e9} onChange={unit_price => patch({unit_price})}/>
    <label>Price source<input required maxLength={1000} value={value.rate_source} onChange={e => patch({rate_source: e.target.value})}/></label>
    <div className="development-fields">
      {(['location_factor', 'access_factor', 'complexity_factor'] as const).map((field, i) => <CostNumber key={field}
        label={['Location ×', 'Access ×', 'Complexity ×'][i]} value={value[field]} min={.001} max={10}
        onChange={n => patch({[field]: n})}/>)}
    </div>
    <details><summary>Converted area</summary>
      <p className="zoning-muted">All physical floors × 100%, including floors excluded from GFA/FAR.</p>
      <div className="development-fields">
        <CostNumber label="Foundation factor" value={value.foundation_factor} max={2} onChange={n => patch({foundation_factor: n!})}/>
        <CostNumber label="Roof factor" value={value.roof_factor} max={2} onChange={n => patch({roof_factor: n!})}/>
      </div>
      <small className="zoning-muted">Initial assumptions: strip foundation 0.5 · concrete roof 0.4. Use 0 for absent items.</small>
      <label>Area / factor source<input required maxLength={1000} value={value.area_source} onChange={e => patch({area_source: e.target.value})}/></label>
      {perBuilding && <>
        <CostNumber label="Contract floor area override (m²)" optional max={1e8} value={value.floor_area_m2} onChange={n => patch({floor_area_m2: n})}/>
        {value.additional_areas.map((area, index) => <fieldset className="cost-area-item" key={index}><legend>Additional item {index+1}</legend>
          <label>Item<input required maxLength={120} value={area.name} onChange={e => patch({additional_areas: value.additional_areas.map((row,i) => i === index ? {...row,name:e.target.value} : row)})}/></label>
          <div className="development-fields">{(['area_m2','factor'] as const).map(field => <CostNumber key={field}
            label={field === 'area_m2' ? 'Area (m²)' : 'Conversion ×'} value={area[field]} max={field === 'factor' ? 5 : 1e8}
            onChange={n => patch({additional_areas: value.additional_areas.map((row,i) => i === index ? {...row,[field]:n} : row)})}/>)}</div>
          <label>Item source<input required maxLength={1000} value={area.source} onChange={e => patch({additional_areas: value.additional_areas.map((row,i) => i === index ? {...row,source:e.target.value} : row)})}/></label>
          <button type="button" aria-label={`Remove additional item ${index+1}`} onClick={() => patch({additional_areas: value.additional_areas.filter((_,i) => i !== index)})}><Trash2 size={16}/></button>
        </fieldset>)}
        <button type="button" disabled={value.additional_areas.length >= 40} onClick={() => patch({additional_areas: [...value.additional_areas,
          {name:'Additional area',area_m2:0,factor:1,source:'User contract assumption'}], additional_areas_confirmed:false})}><Plus size={15}/>Additional area</button>
        {!!value.additional_areas.length && <label className="zoning-check"><input type="checkbox" required checked={value.additional_areas_confirmed}
          onChange={e => patch({additional_areas_confirmed:e.target.checked})}/>Additional items do not overlap counted floors or roof.</label>}
      </>}
    </details>
  </div>;
}
