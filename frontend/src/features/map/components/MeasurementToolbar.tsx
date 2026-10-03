import { Check, RotateCcw, Ruler, TriangleRight } from 'lucide-react';
import { useRef } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapMode, MeasurementState } from '../types/map';
import { calculateMeasurementSummary, formatMeasurementDistance, measurementPhase } from '../utils/measurement';

interface MeasurementToolbarProps {
  measurement: MeasurementState;
  mode: MapMode;
  onToggleComponents: () => void;
  onNew: () => void;
  onDone: () => void;
}

export function MeasurementToolbar({ measurement, mode, onToggleComponents, onNew, onDone }: MeasurementToolbarProps) {
  const toolbarRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      gsap.fromTo(
        toolbarRef.current,
        { y: 20, opacity: 0 },
        { y: 0, opacity: 1, duration: motionDuration(0.32), ease: 'power3.out' },
      );
    },
    { scope: toolbarRef },
  );

  const status = measurement.status === 'complete'
    ? 'Measurement complete'
    : measurement.points.length === 0
      ? 'Click the map to start'
      : `${measurement.points.length} ${measurement.points.length === 1 ? 'point' : 'points'}`;
  const summary = calculateMeasurementSummary(measurement.points);
  const total = mode === '2d' ? summary.totalHorizontalMeters : summary.totalSpatialMeters;
  const snap = measurement.preview?.snap?.kind;

  return (
    <aside
      ref={toolbarRef}
      className="measurement-toolbar glass-panel"
      role="region"
      aria-label="Distance measurement"
      data-phase={measurementPhase(measurement)}
    >
      <div className="measurement-heading" aria-live="polite">
        <Ruler aria-hidden="true" size={18} />
        <div>
          <strong>{status}</strong>
          {measurement.points.length > 0 && (
            <span>{mode === '3d' && !summary.elevationAvailable ? 'Elevation unavailable' : `Total ${formatMeasurementDistance(total)}`}</span>
          )}
          {measurement.status === 'active' && snap && <span className="sr-only">{snap} snap</span>}
        </div>
      </div>
      <div className="measurement-actions">
        {mode === '3d' && (
          <button type="button" className="secondary-button" onClick={onToggleComponents}
            aria-label="Show distance components" aria-pressed={!!measurement.showComponents}
            title="Horizontal and vertical components for unrelated 3D points">
            <TriangleRight aria-hidden="true" size={15} /> Components
          </button>
        )}
        <button type="button" className="secondary-button" onClick={onNew} aria-label="New measurement">
          <RotateCcw aria-hidden="true" size={15} /> New measurement
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={onDone}
          disabled={measurement.points.length < 2 || measurement.status === 'complete'}
          aria-label="Done"
        >
          <Check aria-hidden="true" size={16} /> Done
        </button>
      </div>
    </aside>
  );
}
