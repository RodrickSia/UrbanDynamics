import { LandPlot, Layers2, Map as MapIcon, Satellite } from 'lucide-react';
import { useRef, useState } from 'react';

import type { MapStyleId } from '../config/mapConfig';
import { gsap, motionDuration, useGSAP } from '../motion';
import { MotionIconButton } from './MotionIconButton';

interface MapStyleSelectorProps {
  value: MapStyleId;
  onChange: (value: MapStyleId) => void;
}

export function MapStyleSelector({ value, onChange }: MapStyleSelectorProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useGSAP(
    () => {
      if (!isOpen) return;
      gsap.fromTo(
        '.basemap-picker',
        { autoAlpha: 0, x: 12, scale: 0.96 },
        { autoAlpha: 1, x: 0, scale: 1, duration: motionDuration(0.25), ease: 'power2.out' },
      );
    },
    { scope: rootRef, dependencies: [isOpen], revertOnUpdate: true },
  );

  const selectStyle = (style: MapStyleId) => {
    onChange(style);
    setIsOpen(false);
  };

  return (
    <div
      ref={rootRef}
      className={`basemap-module ${isOpen ? 'is-open' : ''}`}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false); }}
    >
      {isOpen && (
        <div className="basemap-pointer-bridge">
          <section className="basemap-picker glass-panel" role="region" aria-label="Basemap">
            <button type="button" aria-label="Default" aria-pressed={value === 'standard'} onClick={() => selectStyle('standard')}>
              <span className="basemap-preview default-preview" aria-hidden="true"><MapIcon size={18} /></span><span>Default</span>
            </button>
            <button type="button" aria-label="Satellite" aria-pressed={value === 'satellite'} onClick={() => selectStyle('satellite')}>
              <span className="basemap-preview satellite-preview" aria-hidden="true"><Satellite size={18} /></span><span>Satellite</span>
            </button>
            <button type="button" aria-label="Planning" disabled>
              <span className="basemap-preview planning-preview" aria-hidden="true"><LandPlot size={18} /></span><span>Planning</span><small>Unavailable</small>
            </button>
          </section>
        </div>
      )}
      <MotionIconButton
        className="corner-action glass-surface"
        aria-label="Choose basemap"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        <Layers2 aria-hidden="true" size={19} />
      </MotionIconButton>
    </div>
  );
}
