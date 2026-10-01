import { ChevronLeft, CloudSun, MapPin, X } from 'lucide-react';
import { useRef } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { PlaceDetails } from '../types/map';

interface PlaceDetailsPanelProps {
  place: PlaceDetails;
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  onClose: () => void;
}

export function PlaceDetailsPanel(props: PlaceDetailsPanelProps) {
  const panelRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      if (!panelRef.current) return;
      if (props.isCollapsed) {
        gsap.to(panelRef.current, {
          xPercent: -100,
          duration: motionDuration(0.35),
          ease: 'power3.inOut',
        });
        return;
      }
      gsap.fromTo(
        panelRef.current,
        { xPercent: -100 },
        { xPercent: 0, duration: motionDuration(0.4), ease: 'power3.out' },
      );
    },
    { scope: panelRef, dependencies: [props.isCollapsed], revertOnUpdate: true },
  );

  return (
    <aside ref={panelRef} className="place-details-panel glass-panel" aria-label="Place details">
      <button
        className="drawer-collapse-button"
        type="button"
        onClick={props.onToggleCollapsed}
        aria-label={props.isCollapsed ? 'Expand place details' : 'Collapse place details'}
      >
        <ChevronLeft aria-hidden="true" className={props.isCollapsed ? 'is-reversed' : ''} size={20} />
      </button>
      <div className="place-details-hero" aria-hidden="true"><MapPin size={34} /></div>
      <div className="place-details-content">
        <header>
          <div>
            <h1>{props.place.name}</h1>
            <p>{props.place.context}</p>
          </div>
          <button className="quiet-icon-button" type="button" onClick={props.onClose} aria-label="Close place details">
            <X aria-hidden="true" size={18} />
          </button>
        </header>
        <div className="place-weather-row">
          <CloudSun aria-hidden="true" size={22} />
          <div><strong>{props.place.temperatureC}°C</strong><span>{props.place.weatherLabel}</span></div>
        </div>
        <dl className="place-coordinate-list">
          <div><dt>Latitude</dt><dd>{props.place.latitude.toFixed(5)}</dd></div>
          <div><dt>Longitude</dt><dd>{props.place.longitude.toFixed(5)}</dd></div>
        </dl>
      </div>
    </aside>
  );
}
