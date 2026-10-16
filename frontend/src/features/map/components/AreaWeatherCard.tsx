import { CloudSun, MapPin } from 'lucide-react';

import type { PlaceDetails } from '../types/map';

interface AreaWeatherCardProps {
  place: PlaceDetails;
  onSelect: () => void;
}

export function AreaWeatherCard({ place, onSelect }: AreaWeatherCardProps) {
  return (
    <button className="area-weather-card" type="button" onClick={onSelect} aria-label={`Open ${place.name} details`}>
      <span className="area-weather-icon" aria-hidden="true"><MapPin size={17} /></span>
      <span className="area-weather-copy">
        <strong>{place.name}</strong>
        <small>{place.context}</small>
      </span>
      <span className="weather-reading">
        <CloudSun aria-hidden="true" size={20} />
        <strong>{place.temperatureC==null?'—':`${place.temperatureC}°C`}</strong>
      </span>
    </button>
  );
}
