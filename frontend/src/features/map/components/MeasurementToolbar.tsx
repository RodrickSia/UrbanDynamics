import { Check, RotateCcw, Ruler } from 'lucide-react';
import { useMemo, useRef } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapMode, MeasurementState } from '../types/map';
import { calculateMeasurementSummary, formatMeasurementDistance } from '../utils/measurement';

interface MeasurementToolbarProps {
  measurement: MeasurementState;
  mode: MapMode;
  onNew: () => void;
  onDone: () => void;
}

export function MeasurementToolbar({ measurement, mode, onNew, onDone }: MeasurementToolbarProps) {
  const toolbarRef = useRef<HTMLElement>(null);
  const committedSummary = useMemo(
    () => calculateMeasurementSummary(measurement.points),
    [measurement.points],
  );
  const displaySummary = useMemo(
    () => calculateMeasurementSummary(
      measurement.preview ? [...measurement.points, measurement.preview] : measurement.points,
    ),
    [measurement.points, measurement.preview],
  );
  const total = mode === '3d'
    ? committedSummary.totalSpatialMeters
    : committedSummary.totalHorizontalMeters;
  const lastSegment = mode === '3d'
    ? displaySummary.lastSegment?.spatialMeters
    : displaySummary.lastSegment?.horizontalMeters;
  const totalAvailable = mode === '2d'
    || measurement.points.length < 2
    || committedSummary.elevationAvailable;
  const segmentAvailable = mode === '2d'
    || displaySummary.lastSegment == null
    || displaySummary.elevationAvailable;

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

  return (
    <aside
      ref={toolbarRef}
      className="measurement-toolbar glass-panel"
      role="region"
      aria-label="Distance measurement"
    >
      <div className="measurement-heading">
        <Ruler aria-hidden="true" size={18} />
        <div>
          <strong>{status}</strong>
          {measurement.status === 'active' && measurement.points.length > 0 && (
            <span>Click to add another point</span>
          )}
        </div>
      </div>
      <div className="measurement-metrics" aria-live="polite">
        <span>
          <small>{mode === '3d' ? '3D total' : 'Horizontal total'}</small>
          {totalAvailable ? formatMeasurementDistance(total) : '—'}
        </span>
        <span>
          <small>{measurement.preview ? 'Current segment' : 'Last segment'}</small>
          {lastSegment == null || !segmentAvailable ? '—' : formatMeasurementDistance(lastSegment)}
        </span>
        {mode === '3d' && displaySummary.lastSegment && (
          <>
            <span><small>Horizontal</small>{formatMeasurementDistance(displaySummary.lastSegment.horizontalMeters)}</span>
            <span><small>Δ height</small>{segmentAvailable ? formatMeasurementDistance(displaySummary.lastSegment.verticalMeters) : '—'}</span>
          </>
        )}
        {mode === '3d' && measurement.points.length > 0 && !displaySummary.elevationAvailable && (
          <span className="measurement-warning">Elevation unavailable</span>
        )}
      </div>
      <div className="measurement-actions">
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
