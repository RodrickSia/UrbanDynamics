import { Layers3, LocateFixed, Minus, Plus } from 'lucide-react';
import { useRef } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapControlAction, MapMode } from '../types/map';
import { MotionIconButton } from './MotionIconButton';

interface MapNavigationControlsProps {
  mode: MapMode;
  rightPanelOpen: boolean;
  layersOpen: boolean;
  onModeChange: (mode: MapMode) => void;
  onToggleLayers: () => void;
  onCommand: (action: MapControlAction) => void;
}

export function MapNavigationControls(props: MapNavigationControlsProps) {
  const modeIconRef = useRef<HTMLSpanElement>(null);

  useGSAP(
    () => {
      gsap.fromTo(
        modeIconRef.current,
        { y: 16, autoAlpha: 0, scale: 0.9, rotationX: -28 },
        {
          y: 0,
          autoAlpha: 1,
          scale: 1,
          rotationX: 0,
          duration: motionDuration(0.38),
          ease: 'power3.out',
          overwrite: 'auto',
        },
      );
    },
    { scope: modeIconRef, dependencies: [props.mode], revertOnUpdate: true },
  );

  const nextMode: MapMode = props.mode === '2d' ? '3d' : '2d';

  return (
    <nav
      className="navigation-cluster"
      data-testid="navigation-cluster"
      data-right-panel-open={props.rightPanelOpen}
      aria-label="Map navigation"
    >
      <div className="navigation-buttons glass-surface">
        <MotionIconButton onClick={() => props.onCommand('zoom-in')} aria-label="Zoom in"><Plus aria-hidden="true" size={19} /></MotionIconButton>
        <MotionIconButton onClick={() => props.onCommand('zoom-out')} aria-label="Zoom out"><Minus aria-hidden="true" size={19} /></MotionIconButton>
        <MotionIconButton onClick={() => props.onCommand('locate')} aria-label="Locate me"><LocateFixed aria-hidden="true" size={18} /></MotionIconButton>
      </div>
      <MotionIconButton
        className="navigation-action glass-surface"
        aria-label={`Switch to ${nextMode.toUpperCase()}`}
        aria-pressed={props.mode === '3d'}
        onClick={() => props.onModeChange(nextMode)}
      >
        <span ref={modeIconRef} className="mode-icon" aria-hidden="true">
          {props.mode.toUpperCase()}
        </span>
      </MotionIconButton>
      <MotionIconButton
        className={`navigation-action glass-surface ${props.layersOpen ? 'is-active' : ''}`}
        aria-label={props.layersOpen ? 'Close data layers' : 'Open data layers'}
        aria-expanded={props.layersOpen}
        onClick={props.onToggleLayers}
      >
        <Layers3 aria-hidden="true" size={19} />
      </MotionIconButton>
    </nav>
  );
}
