import type { Map as MapLibreMap } from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import type { MapControlRequest, MapFocusRequest, UserLocation } from '../types/map';

interface MapCommandOptions {
  mapRef: RefObject<MapLibreMap | null>;
  focusRequest: MapFocusRequest | null;
  controlRequest: MapControlRequest | null;
  onStatusChange: (ready: boolean, message: string) => void;
  onUserLocationChange: (location: UserLocation) => void;
}

export function useMapCommands(options: MapCommandOptions) {
  const {
    mapRef,
    focusRequest,
    controlRequest,
    onStatusChange,
    onUserLocationChange,
  } = options;

  useEffect(() => {
    if (!focusRequest) return;
    mapRef.current?.easeTo({
      center: focusRequest.center,
      zoom: focusRequest.zoom,
      duration: 900,
    });
  }, [focusRequest, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !controlRequest) return;

    if (controlRequest.action === 'zoom-in') {
      map.zoomIn({ duration: 280 });
      return;
    }
    if (controlRequest.action === 'zoom-out') {
      map.zoomOut({ duration: 280 });
      return;
    }
    if (!navigator.geolocation) {
      onStatusChange(false, 'This browser does not support geolocation');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (mapRef.current !== map) return;
        map.easeTo({
          center: [coords.longitude, coords.latitude],
          zoom: Math.max(map.getZoom(), 13),
          duration: 900,
        });
        onUserLocationChange({
          longitude: coords.longitude,
          latitude: coords.latitude,
        });
        onStatusChange(true, 'Showing your location');
      },
      () => onStatusChange(false, 'Your location could not be accessed'),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 },
    );
  }, [controlRequest, mapRef, onStatusChange, onUserLocationChange]);
}
