import { MapPin, Search, X } from 'lucide-react';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { PlaceDetails } from '../types/map';
import { AreaWeatherCard } from './AreaWeatherCard';

interface SearchBoxProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectPlace: (place: PlaceDetails) => void;
}

const INITIAL_RECENT_PLACES: PlaceDetails[] = [
  {
    id: 'hanoi',
    name: 'Hanoi',
    context: 'Vietnam',
    longitude: 105.8342,
    latitude: 21.0278,
    temperatureC: 28,
    weatherLabel: 'Partly cloudy',
  },
  {
    id: 'ho-chi-minh-city',
    name: 'Ho Chi Minh City',
    context: 'Vietnam',
    longitude: 106.6297,
    latitude: 10.8231,
    temperatureC: 31,
    weatherLabel: 'Cloudy',
  },
  {
    id: 'da-nang',
    name: 'Da Nang',
    context: 'Vietnam',
    longitude: 108.2022,
    latitude: 16.0544,
    temperatureC: 29,
    weatherLabel: 'Mostly sunny',
  },
];

const CURRENT_AREA: PlaceDetails = {
  id: 'current-area',
  name: 'Ba Dinh',
  context: 'Hanoi',
  longitude: 105.8142,
  latitude: 21.0338,
  temperatureC: 28,
  weatherLabel: 'Partly cloudy',
};

export function SearchBox({ isOpen, onOpenChange, onSelectPlace }: SearchBoxProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [recentPlaces, setRecentPlaces] = useState(INITIAL_RECENT_PLACES);

  useEffect(() => {
    if (!isOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onOpenChange(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [isOpen, onOpenChange]);

  useGSAP(
    () => {
      if (!isOpen) return;
      gsap.fromTo(
        '.search-workspace',
        { autoAlpha: 0, y: -10 },
        { autoAlpha: 1, y: 0, duration: motionDuration(0.28), ease: 'power2.out' },
      );
    },
    { scope: rootRef, dependencies: [isOpen], revertOnUpdate: true },
  );

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return;
    const match = recentPlaces.find((place) =>
      `${place.name} ${place.context}`.toLocaleLowerCase().includes(normalizedQuery),
    );
    if (match) {
      onSelectPlace(match);
      onOpenChange(false);
    }
  };

  const selectPlace = (place: PlaceDetails) => {
    setQuery(place.name);
    setRecentPlaces((current) => [place, ...current.filter((item) => item.id !== place.id)].slice(0, 5));
    onSelectPlace(place);
    onOpenChange(false);
  };

  return (
    <div ref={rootRef} className={`search-module ${isOpen ? 'is-open' : ''}`}>
      <form className="search-shell glass-surface" role="search" onSubmit={submitSearch}>
        <Search aria-hidden="true" size={19} />
        <label className="sr-only" htmlFor="location-search">Search places</label>
        <input
          id="location-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => onOpenChange(true)}
          placeholder="Search places"
          autoComplete="off"
        />
        {query && (
          <button className="quiet-icon-button" type="button" onClick={() => setQuery('')} aria-label="Clear search">
            <X aria-hidden="true" size={16} />
          </button>
        )}
      </form>

      {isOpen && (
        <section className="search-workspace glass-panel" role="region" aria-label="Search workspace">
          <div className="search-section-heading">
            <span>Recent</span>
          </div>
          {recentPlaces.length ? (
            <ul className="recent-place-list">
              {recentPlaces.map((place) => (
                <li key={place.id}>
                  <button
                    className="recent-place"
                    type="button"
                    onClick={() => selectPlace(place)}
                    aria-label={`${place.name}, ${place.context}`}
                  >
                    <span className="result-icon" aria-hidden="true"><MapPin size={16} /></span>
                    <span><strong>{place.name}</strong><small>{place.context}</small></span>
                  </button>
                  <button
                    className="quiet-icon-button"
                    type="button"
                    onClick={() => setRecentPlaces((items) => items.filter((item) => item.id !== place.id))}
                    aria-label={`Remove ${place.name} from history`}
                  >
                    <X aria-hidden="true" size={14} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="compact-empty-state">No recent places.</p>
          )}
          <div className="search-section-heading this-area-heading">This area</div>
          <AreaWeatherCard place={CURRENT_AREA} onSelect={() => selectPlace(CURRENT_AREA)} />
        </section>
      )}
    </div>
  );
}
