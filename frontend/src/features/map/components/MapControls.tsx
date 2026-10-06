import { Trash2 } from 'lucide-react';

import type { MapStyleId } from '../config/mapConfig';
import type { MapMode, MeasurementKind, MeasurementState, TimeRange } from '../types/map';
import type { MeasurementUnits } from '../utils/measurementUnits';
import { AreaMeasurementToolbar } from './AreaMeasurementToolbar';
import { MeasurementSelector } from './MeasurementSelector';
import { MapStyleSelector } from './MapStyleSelector';
import { MeasurementToolbar } from './MeasurementToolbar';
import { MotionIconButton } from './MotionIconButton';
import { TimeRangeSelector } from './TimeRangeSelector';

interface MapControlsProps {
  viewshedActive?: boolean;
  onViewshed?: () => void;
  measurement: MeasurementState;
  mode: MapMode;
  rightPanelOpen: boolean;
  hasSelection: boolean;
  mapStyle: MapStyleId;
  timeRange: TimeRange;
  onMapStyleChange: (style: MapStyleId) => void;
  onTimeRangeChange: (range: TimeRange) => void;
  onStartMeasurement: (kind?: MeasurementKind) => void;
  onMeasurementUnitsChange: (units: MeasurementUnits) => void;
  onUndoMeasurementPoint: () => void;
  onCancelMeasurement: () => void;
  onCompleteMeasurement: () => void;
  onToggleMeasurementComponents: () => void;
  onClearSelection: () => void;
}

export function MapControls(props: MapControlsProps) {
  const isMeasuring = props.measurement.status !== 'idle';

  return (
    <>
      {isMeasuring && !props.viewshedActive && (props.measurement.kind === 'area' ?
        <AreaMeasurementToolbar measurement={props.measurement} mode={props.mode}
          onUnitsChange={props.onMeasurementUnitsChange} onUndo={props.onUndoMeasurementPoint}
          onClear={props.onCancelMeasurement} onNew={() => props.onStartMeasurement()}
          onDone={props.onCompleteMeasurement} /> :
        <MeasurementToolbar
          measurement={props.measurement}
          mode={props.mode}
          onToggleComponents={props.onToggleMeasurementComponents}
          onNew={() => props.onStartMeasurement()}
          onClear={props.onCancelMeasurement}
          onUnitsChange={props.onMeasurementUnitsChange}
          onDone={props.onCompleteMeasurement}
        />
      )}
      <div className="corner-tools" data-right-panel-open={props.rightPanelOpen} aria-label="Map tools">
        {props.hasSelection && !isMeasuring && (
          <MotionIconButton className="corner-action glass-surface" onClick={props.onClearSelection} aria-label="Clear selection"><Trash2 aria-hidden="true" size={18} /></MotionIconButton>
        )}
        <TimeRangeSelector value={props.timeRange} onChange={props.onTimeRangeChange} />
        <MeasurementSelector measurement={props.measurement} onSelect={props.onStartMeasurement}
          viewshedActive={props.viewshedActive} onViewshed={props.onViewshed} />
        <MapStyleSelector value={props.mapStyle} onChange={props.onMapStyleChange} />
      </div>
    </>
  );
}
