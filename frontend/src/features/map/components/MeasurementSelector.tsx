import { Eye, Pentagon, Ruler } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { MeasurementKind, MeasurementState } from '../types/map';
import { MotionIconButton } from './MotionIconButton';

export function MeasurementSelector({ measurement, onSelect, viewshedActive = false, onViewshed }: {
  measurement: MeasurementState;
  onSelect: (kind: MeasurementKind) => void;
  viewshedActive?: boolean;
  onViewshed?: () => void;
}) {
  const [open,setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const active = measurement.status !== 'idle' && !viewshedActive;
  useGSAP(() => {
    if (!open) return;
    gsap.fromTo('.measurement-picker', { autoAlpha:0, x:12, scale:0.94 },
      { autoAlpha:1, x:0, scale:1, duration:motionDuration(0.26), ease:'power3.out' });
  }, { scope:rootRef, dependencies:[open], revertOnUpdate:true });
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown',dismiss);
    return () => document.removeEventListener('pointerdown',dismiss);
  }, [open]);
  const select = (kind: MeasurementKind) => {
    if (!active || (measurement.kind ?? 'distance') !== kind) onSelect(kind);
    setOpen(false);
    rootRef.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus();
  };
  return <div className="measurement-module" ref={rootRef}
    onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}
    onKeyDown={e => {
      if (e.key === 'Escape' && open) {
        setOpen(false); e.stopPropagation();
        rootRef.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus();
      }
    }}>
    <MotionIconButton className={`corner-action glass-surface ${active || viewshedActive ? 'is-active' : ''}`}
      aria-label="Measurement tools" aria-expanded={open} onClick={() => setOpen(value => !value)}>
      <Ruler size={19} aria-hidden="true" />
    </MotionIconButton>
    {open && <div className="measurement-picker solid-panel" role="group" aria-label="Choose measurement">
      <MotionIconButton className="corner-action" aria-label="Measure distance" title="Distance"
        aria-pressed={active && (measurement.kind ?? 'distance') === 'distance'} onClick={() => select('distance')}>
        <Ruler size={19} aria-hidden="true" />
      </MotionIconButton>
      <MotionIconButton className="corner-action" aria-label="Measure area" title="Area"
        aria-pressed={active && measurement.kind === 'area'} onClick={() => select('area')}>
        <Pentagon size={19} aria-hidden="true" />
      </MotionIconButton>
      {onViewshed && <MotionIconButton className="corner-action" aria-label="Viewshed" title="Viewshed"
        aria-pressed={viewshedActive} onClick={() => { onViewshed(); setOpen(false); rootRef.current?.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus(); }}>
        <Eye size={19} aria-hidden="true" />
      </MotionIconButton>}
    </div>}
  </div>;
}
