import { useEffect, useMemo, useState } from 'react';
import { zoningRequest } from './api';
import { areaText } from './geometry';
import type { CurrentLandUse, Plan } from './types';

const requests = new Map<string, Promise<CurrentLandUse>>();

export function CurrentParcelUse({ plan }: { plan: Plan }) {
  const [result, setResult] = useState<{ key: string; data?: CurrentLandUse; error?: string } | null>(null);
  const areaKey = useMemo(() => JSON.stringify(plan.study_area), [plan.study_area]);
  const key = `${plan.id}/${areaKey}`;
  useEffect(() => {
    let active = true;
    let request = requests.get(key);
    if (!request) {
      request = zoningRequest<CurrentLandUse>(`/${plan.id}/land-use`);
      requests.set(key, request);
      void request.catch(() => requests.delete(key));
    }
    void request.then(data => { if (active) setResult({ key, data }); })
      .catch(() => { if (active) setResult({ key, error: 'Parcel data unavailable' }); });
    return () => { active = false; };
  }, [plan.id, key]);
  const rows = result?.key === key ? result.data?.rows : undefined;
  const total = rows?.reduce((sum, row) => sum + row.area_m2, 0) ?? 0;
  return <section className="zoning-distribution" aria-label="Current parcel land use">
    <h3>Current land use <span className="zoning-count">Parcels</span></h3>
    {!result || result.key !== key ? <p role="status" className="zoning-muted">Loading parcels…</p>
      : result.error ? <p role="status" className="zoning-muted">{result.error}</p>
      : !rows?.length ? <p className="zoning-muted">No mapped parcels in this area.</p>
      : <>
        <div className="zoning-area-strip" role="img" aria-label={`Current parcel land use, ${rows.length} source codes`}>
          {rows.map(row => <span key={row.code ?? 'unknown'} style={{ flexGrow: row.area_m2 / total, backgroundColor: row.color }}
            title={`${row.code ?? 'Unknown'} · ${areaText(row.area_m2)}`}/>)}
        </div>
        <ul className="zoning-land-use-list">{rows.slice(0, 6).map(row => <li key={row.code ?? 'unknown'}>
          <i className="zoning-swatch" style={{ backgroundColor: row.color }}/>
          <span>{row.code ?? 'Unknown'} <small>{row.category ?? 'Unclassified'}</small></span>
          <strong>{areaText(row.area_m2)}</strong>
        </li>)}</ul>
        {rows.length > 6 && <details><summary>{rows.length - 6} more codes</summary><ul className="zoning-land-use-list">{rows.slice(6).map(row => <li key={row.code ?? 'unknown'}>
          <i className="zoning-swatch" style={{ backgroundColor: row.color }}/><span>{row.code ?? 'Unknown'}</span><strong>{areaText(row.area_m2)}</strong>
        </li>)}</ul></details>}
      </>}
  </section>;
}
