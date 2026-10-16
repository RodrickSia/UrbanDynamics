import { MapPin, Search, X } from 'lucide-react';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { PlaceDetails } from '../types/map';
import { AreaWeatherCard } from './AreaWeatherCard';
import { API_BASE_URL } from '../../../services/api';

type PlaceSuggestion = {id:string;name:string;context:string};

interface SearchBoxProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectPlace: (place: PlaceDetails) => void;
  onWorkspaceHeightChange: (height: number) => void;
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

export function SearchBox({ isOpen, onOpenChange, onSelectPlace, onWorkspaceHeightChange }: SearchBoxProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [recentPlaces, setRecentPlaces] = useState(INITIAL_RECENT_PLACES);
  const [results,setResults]=useState<PlaceSuggestion[]>([]);
  const [loading,setLoading]=useState(false),[searchError,setSearchError]=useState('');
  const [selecting,setSelecting]=useState(false);
  const selectionRequest=useRef(0);

  useEffect(()=>{
    const controller=new AbortController();
    ++selectionRequest.current;setSelecting(false);
    setResults([]);setSearchError('');
    if(!isOpen||query.trim().length<3){setLoading(false);return;}
    setLoading(true);
    const timer=window.setTimeout(async()=>{
      try{
        const response=await fetch(`${API_BASE_URL}/api/v1/places/search?q=${encodeURIComponent(query.trim())}`,{signal:controller.signal});
        const data=await response.json();
        if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Place search unavailable');
        if(!controller.signal.aborted)setResults(data.results??[]);
      }catch(error){if(!controller.signal.aborted)setSearchError(error instanceof Error?error.message:'Place search unavailable');}
      finally{if(!controller.signal.aborted)setLoading(false);}
    },350);
    return ()=>{controller.abort();window.clearTimeout(timer);};
  },[query,isOpen]);

  const chooseSuggestion=async(suggestion:PlaceSuggestion)=>{
    const version=++selectionRequest.current;
    setSelecting(true);setSearchError('');
    try{
      const response=await fetch(`${API_BASE_URL}/api/v1/places/detail?place_id=${encodeURIComponent(suggestion.id)}`,{signal:AbortSignal.timeout(20000)});
      const place=await response.json();
      if(!response.ok)throw Error(typeof place.detail==='string'?place.detail:'Place details unavailable');
      if(version!==selectionRequest.current)return;
      selectPlace(place);
    }catch(error){if(version===selectionRequest.current)setSearchError(error instanceof Error?error.message:'Place details unavailable');}
    finally{if(version===selectionRequest.current)setSelecting(false);}
  };

  useEffect(() => {
    if (!isOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onOpenChange(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [isOpen, onOpenChange]);

  useEffect(() => {
    if (!isOpen) {
      onWorkspaceHeightChange(0);
      return;
    }
    const panel = rootRef.current?.querySelector('.search-workspace');
    if (!panel) return;
    const updateHeight = () => onWorkspaceHeightChange(panel.getBoundingClientRect().height);
    updateHeight();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateHeight);
    observer.observe(panel);
    return () => observer.disconnect();
  }, [isOpen, onWorkspaceHeightChange]);

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
    if(results.length&&!loading){void chooseSuggestion(results[0]);return;}
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
      <form className="search-shell solid-panel" role="search" onSubmit={submitSearch}>
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
        <section className="search-workspace solid-panel" role="region" aria-label="Search workspace">
          {query.trim().length>=3&&<>
            <div className="search-section-heading"><span>Search results · Goong</span></div>
            {loading&&<p className="compact-empty-state" role="status">Searching places…</p>}
            {selecting&&<p className="compact-empty-state" role="status">Opening place…</p>}
            {searchError&&<p className="compact-empty-state" role="alert">{searchError}</p>}
            {!loading&&!searchError&&!results.length&&<p className="compact-empty-state">No matching places.</p>}
            {!!results.length&&<ul className="recent-place-list">{results.map(place=><li key={place.id}><button className="recent-place" type="button" disabled={selecting} onClick={()=>void chooseSuggestion(place)} aria-label={`${place.name}, ${place.context}`}><span className="result-icon" aria-hidden="true"><MapPin size={16}/></span><span><strong>{place.name}</strong><small>{place.context}</small></span></button></li>)}</ul>}
          </>}
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
