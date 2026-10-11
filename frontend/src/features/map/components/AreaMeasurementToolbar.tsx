import { Check, Pentagon, RotateCcw, Trash2, Undo2 } from 'lucide-react';
import { useMemo, useRef } from 'react';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapMode, MeasurementState } from '../types/map';
import { calculateAreaMeasurement } from '../utils/measurementArea';
import { formatArea, formatLength, type MeasurementUnits } from '../utils/measurementUnits';

export function AreaMeasurementToolbar({ measurement, mode, onUnitsChange, onUndo, onClear, onNew, onDone }: {
  measurement: MeasurementState; mode: MapMode;
  onUnitsChange: (units: MeasurementUnits) => void;
  onUndo: () => void; onClear: () => void; onNew: () => void; onDone: () => void;
}) {
  const rootRef = useRef<HTMLElement>(null);
  useGSAP(() => {
    gsap.fromTo(rootRef.current,{ y:20,autoAlpha:0 },
      { y:0,autoAlpha:1,duration:motionDuration(0.32),ease:'power3.out' });
  }, { scope:rootRef });
  const committed = useMemo(() => calculateAreaMeasurement(measurement.points,mode), [measurement.points,mode]);
  const current = useMemo(() => measurement.status === 'active' && measurement.preview
    ? calculateAreaMeasurement([...measurement.points,measurement.preview],mode) : committed,
  [measurement,mode,committed]);
  const units = measurement.units ?? 'metric';
  return <aside ref={rootRef} className="measurement-toolbar area-toolbar solid-panel" role="region" aria-label="Area measurement">
    <div className="measurement-heading">
      <Pentagon aria-hidden="true" size={19} />
      <div>
        <strong>{current.valid ? formatArea(current.areaSquareMeters,units)
          : measurement.points.length ? `${measurement.points.length} vertices` : 'Place vertices'}</strong>
        {current.valid && <span>Perimeter {formatLength(current.perimeterMeters,units)}</span>}
        <span className="area-mode">{current.valid ? current.calculationMode === 'planar' ? '3D plane' : 'Horizontal projection' : current.reason}</span>
        {current.valid && !current.elevationAvailable && <span>Elevation unavailable</span>}
      </div>
    </div>
    <div className="measurement-actions">
      <select className="measurement-unit-select" aria-label="Measurement units" value={units}
        onChange={event => onUnitsChange(event.target.value as MeasurementUnits)}>
        <option value="metric">Metric</option><option value="imperial">Imperial</option>
      </select>
      <button type="button" className="secondary-button measurement-icon-action" aria-label="Undo last vertex" title="Undo last vertex"
        disabled={!measurement.points.length} onClick={onUndo}><Undo2 size={16} aria-hidden="true" /></button>
      <button type="button" className="secondary-button measurement-icon-action" aria-label="New measurement" title="New measurement" onClick={onNew}>
        <RotateCcw size={15} aria-hidden="true" />
      </button>
      <button type="button" className="primary-button" aria-label="Done" onClick={onDone}
        disabled={!committed.valid || measurement.status === 'complete'}><Check size={16} aria-hidden="true" /> Done</button>
      <button type="button" className="secondary-button measurement-icon-action" aria-label="Clear measurement" title="Clear measurement" onClick={onClear}>
        <Trash2 size={16} aria-hidden="true" />
      </button>
    </div>
    <span className="sr-only" role="status">{measurement.status === 'complete' ? 'Area measurement complete' : `${measurement.points.length} vertices selected`}</span>
  </aside>;
}
