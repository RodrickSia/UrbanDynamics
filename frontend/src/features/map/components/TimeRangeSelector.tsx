import { Clock3 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import { TIME_RANGE_OPTIONS, type TimeRange } from '../types/map';
import { MotionIconButton } from './MotionIconButton';

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
}

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [isOpen]);

  useGSAP(
    () => {
      if (!isOpen) return;
      gsap.fromTo(
        '.time-range-popover',
        { autoAlpha: 0, x: 12, scale: 0.96 },
        { autoAlpha: 1, x: 0, scale: 1, duration: motionDuration(0.25), ease: 'power2.out' },
      );
    },
    { scope: rootRef, dependencies: [isOpen], revertOnUpdate: true },
  );

  return (
    <div ref={rootRef} className="time-range-module">
      {isOpen && (
        <section className="time-range-popover glass-panel" role="region" aria-label="Time range">
          {TIME_RANGE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-label={option.label}
              aria-pressed={value === option.value}
              onClick={() => { onChange(option.value); setIsOpen(false); }}
            >
              {option.label}
            </button>
          ))}
        </section>
      )}
      <MotionIconButton
        className={`corner-action glass-surface ${isOpen ? 'is-active' : ''}`}
        aria-label={isOpen ? 'Close time range' : 'Open time range'}
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <Clock3 aria-hidden="true" size={19} />
      </MotionIconButton>
    </div>
  );
}
