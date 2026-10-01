import { Check, Pentagon, Trash2, X } from 'lucide-react';
import { useRef } from 'react';

import type { MapStyleId } from '../config/mapConfig';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { TimeRange } from '../types/map';
import { MapStyleSelector } from './MapStyleSelector';
import { MotionIconButton } from './MotionIconButton';
import { TimeRangeSelector } from './TimeRangeSelector';

interface MapControlsProps {
  isDrawing: boolean;
  rightPanelOpen: boolean;
  draftVertexCount: number;
  hasSelection: boolean;
  mapStyle: MapStyleId;
  timeRange: TimeRange;
  onMapStyleChange: (style: MapStyleId) => void;
  onTimeRangeChange: (range: TimeRange) => void;
  onStartDrawing: () => void;
  onCancelDrawing: () => void;
  onCompleteDrawing: () => void;
  onClearSelection: () => void;
}

export function MapControls(props: MapControlsProps) {
  const workspaceRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      if (!props.isDrawing) return;
      gsap.fromTo(
        workspaceRef.current,
        { y: 20, autoAlpha: 0 },
        { y: 0, autoAlpha: 1, duration: motionDuration(0.32), ease: 'power3.out' },
      );
    },
    { scope: workspaceRef, dependencies: [props.isDrawing], revertOnUpdate: true },
  );

  return (
    <>
      {props.isDrawing && (
        <aside ref={workspaceRef} className="draw-toolbar glass-panel" role="region" aria-label="Polygon drawing">
          <div className="draw-status">
            <Pentagon aria-hidden="true" size={18} />
            <strong>{props.draftVertexCount < 3 ? `${props.draftVertexCount}/3 points` : `${props.draftVertexCount} points`}</strong>
          </div>
          <div className="draw-progress" aria-hidden="true">
            {[0, 1, 2].map((index) => <span className={props.draftVertexCount > index ? 'is-complete' : ''} key={index} />)}
          </div>
          <div className="draw-actions">
            <MotionIconButton className="quiet-icon-button" onClick={props.onCancelDrawing} aria-label="Cancel polygon drawing"><X aria-hidden="true" size={17} /></MotionIconButton>
            <button
              type="button"
              className="primary-button"
              onClick={props.onCompleteDrawing}
              disabled={props.draftVertexCount < 3}
              aria-label="Finish polygon"
            >
              <Check aria-hidden="true" size={16} /> Finish
            </button>
          </div>
        </aside>
      )}
      <div className="corner-tools" data-right-panel-open={props.rightPanelOpen} aria-label="Map tools">
        {props.hasSelection && !props.isDrawing && (
          <MotionIconButton className="corner-action glass-surface" onClick={props.onClearSelection} aria-label="Clear selection"><Trash2 aria-hidden="true" size={18} /></MotionIconButton>
        )}
        <TimeRangeSelector value={props.timeRange} onChange={props.onTimeRangeChange} />
        <MotionIconButton
          className={`corner-action glass-surface ${props.isDrawing ? 'is-active' : ''}`}
          onClick={props.isDrawing ? props.onCancelDrawing : props.onStartDrawing}
          aria-label={props.isDrawing ? 'Cancel polygon drawing' : 'Draw polygon'}
          aria-pressed={props.isDrawing}
        >
          <Pentagon aria-hidden="true" size={19} />
        </MotionIconButton>
        <MapStyleSelector value={props.mapStyle} onChange={props.onMapStyleChange} />
      </div>
    </>
  );
}
