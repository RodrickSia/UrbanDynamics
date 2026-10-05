export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '';

export const FUTURE_API_ENDPOINTS = {
  autocomplete: '/api/v1/maps/autocomplete',
  geocode: '/api/v1/maps/geocode',
  reverseGeocode: '/api/v1/maps/reverse-geocode',
  currentWeather: '/api/v1/weather/current',
  population: '/api/v1/urban/population',
  facilities: '/api/v1/urban/facilities',
  traffic: '/api/v1/urban/traffic',
  rain: '/api/v1/urban/rain',
  flood: '/api/v1/urban/flood',
  planning: '/api/v1/urban/planning',
  landPrice: '/api/v1/urban/land-price',
  roadDensity: '/api/v1/urban/road-density',
  greenArea: '/api/v1/urban/green-area',
} as const;
