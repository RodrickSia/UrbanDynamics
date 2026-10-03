import { Ruler, Trash2 } from 'lucide-react';

import type { MapStyleId } from '../config/mapConfig';
import type { MapMode, MeasurementState, TimeRange } from '../types/map';
import { MapStyleSelector } from './MapStyleSelector';
import { MeasurementToolbar } from './MeasurementToolbar';
import { MotionIconButton } from './MotionIconButton';
import { TimeRangeSelector } from './TimeRangeSelector';

interface MapControlsProps {
  measurement: MeasurementState;
  mode: MapMode;
  rightPanelOpen: boolean;
  hasSelection: boolean;
  mapStyle: MapStyleId;
  timeRange: TimeRange;
  onMapStyleChange: (style: MapStyleId) => void;
  onTimeRangeChange: (range: TimeRange) => void;
  onStartMeasurement: () => void;
  onCancelMeasurement: () => void;
  onCompleteMeasurement: () => void;
  onClearSelection: () => void;
}

export function MapControls(props: MapControlsProps) {
  const isMeasuring = props.measurement.status !== 'idle';

  return (
    <>
      {isMeasuring && (
        <MeasurementToolbar
          measurement={props.measurement}
          mode={props.mode}
          onNew={props.onStartMeasurement}
          onDone={props.onCompleteMeasurement}
        />
      )}
      <div className="corner-tools" data-right-panel-open={props.rightPanelOpen} aria-label="Map tools">
        {props.hasSelection && !isMeasuring && (
          <MotionIconButton className="corner-action glass-surface" onClick={props.onClearSelection} aria-label="Clear selection"><Trash2 aria-hidden="true" size={18} /></MotionIconButton>
        )}
        <TimeRangeSelector value={props.timeRange} onChange={props.onTimeRangeChange} />
        <MotionIconButton
          className={`corner-action glass-surface ${isMeasuring ? 'is-active' : ''}`}
          onClick={isMeasuring ? props.onCancelMeasurement : props.onStartMeasurement}
          aria-label={isMeasuring ? 'Close distance measurement' : 'Measure distance'}
          aria-pressed={isMeasuring}
        >
          <Ruler aria-hidden="true" size={19} />
        </MotionIconButton>
        <MapStyleSelector value={props.mapStyle} onChange={props.onMapStyleChange} />
      </div>
    </>
  );
}
