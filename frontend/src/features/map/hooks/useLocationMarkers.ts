import type { Map as MapLibreMap, Marker } from 'maplibre-gl';
import { type RefObject, useEffect, useRef } from 'react';

import type { MapSelection, UserLocation } from '../types/map';
import { createLocationMarkerElement } from '../utils/locationMarkers';

type MarkerConstructor = typeof import('maplibre-gl').Marker;

export function useLocationMarkers(
  mapRef: RefObject<MapLibreMap | null>,
  markerConstructorRef: RefObject<MarkerConstructor | null>,
  mapRevision: number,
  selection: MapSelection,
  userLocation: UserLocation | null,
) {
  const selectedMarkerRef = useRef<Marker | null>(null);
  const userMarkerRef = useRef<Marker | null>(null);

  useEffect(() => {
    selectedMarkerRef.current?.remove();
    selectedMarkerRef.current = null;
    const map = mapRef.current;
    const MarkerClass = markerConstructorRef.current;
    if (!map || !MarkerClass || selection?.kind !== 'point') return;
    const marker = new MarkerClass({
      element: createLocationMarkerElement('selected'),
      anchor: 'bottom',
    })
      .setLngLat([selection.longitude, selection.latitude])
      .addTo(map);
    selectedMarkerRef.current = marker;
    return () => {
      marker.remove();
      if (selectedMarkerRef.current === marker) selectedMarkerRef.current = null;
    };
  }, [mapRef, mapRevision, markerConstructorRef, selection]);

  useEffect(() => {
    userMarkerRef.current?.remove();
    userMarkerRef.current = null;
    const map = mapRef.current;
    const MarkerClass = markerConstructorRef.current;
    if (!map || !MarkerClass || !userLocation) return;
    const marker = new MarkerClass({
      element: createLocationMarkerElement('user'),
      anchor: 'center',
    })
      .setLngLat([userLocation.longitude, userLocation.latitude])
      .addTo(map);
    userMarkerRef.current = marker;
    return () => {
      marker.remove();
      if (userMarkerRef.current === marker) userMarkerRef.current = null;
    };
  }, [mapRef, mapRevision, markerConstructorRef, userLocation]);
}
