import type { Position } from 'geojson';
import { type PointerEvent as ReactPointerEvent, useCallback, useRef, useState } from 'react';

import type { MapStyleId } from '../config/mapConfig';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import {
  createInitialLayerOpacity,
  createInitialLayerState,
  setLayerOpacity,
  setMapMode,
  toggleLayerState,
} from '../state/layerState';
import type {
  MapControlAction,
  MapControlRequest,
  MapFocusRequest,
  MapMode,
  MapSelection,
  PlaceDetails,
  PointSelection,
  TimeRange,
  UrbanLayerDefinition,
  UserLocation,
} from '../types/map';
import { createPolygonSelection } from '../utils/geo';

export type RightPanel = 'layers' | 'polygon' | null;

export function useMapWorkspace() {
  const lastMapSearchDismissalRef = useRef(0);
  const [mode, setMode] = useState<MapMode>('2d');
  const [mapStyle, setMapStyle] = useState<MapStyleId>('standard');
  const [timeRange, setTimeRange] = useState<TimeRange>('1d');
  const [layers, setLayers] = useState(() => createInitialLayerState(URBAN_LAYERS));
  const [opacityByLayer, setOpacityByLayer] = useState(() => createInitialLayerOpacity(URBAN_LAYERS));
  const [selection, setSelection] = useState<MapSelection>(null);
  const [selectedPlace, setSelectedPlace] = useState<PlaceDetails | null>(null);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);
  const [draftCoordinates, setDraftCoordinates] = useState<Position[]>([]);
  const [rightPanel, setRightPanel] = useState<RightPanel>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isPlaceDetailsCollapsed, setIsPlaceDetailsCollapsed] = useState(false);
  const [mapControlRequest, setMapControlRequest] = useState<MapControlRequest | null>(null);
  const [mapFocusRequest, setMapFocusRequest] = useState<MapFocusRequest | null>(null);
  const [mapStatus, setMapStatus] = useState('Map is loading');

  const handleModeChange = useCallback((nextMode: MapMode) => {
    setMode(nextMode);
    setLayers((current) => setMapMode(current, nextMode).layers);
  }, []);

  const handleLayerToggle = useCallback(
    (layer: UrbanLayerDefinition) => {
      if (layer.id === 'buildings-3d') {
        handleModeChange(mode === '3d' ? '2d' : '3d');
        return;
      }
      setLayers((current) => toggleLayerState(current, layer));
    },
    [handleModeChange, mode],
  );

  const startDrawing = useCallback(() => {
    setIsSearchOpen(false);
    setSelectedPlace(null);
    setSelection(null);
    setDraftCoordinates([]);
    setRightPanel('polygon');
  }, []);

  const cancelDrawing = useCallback(() => {
    setDraftCoordinates([]);
    setRightPanel(null);
  }, []);

  const completeDrawing = useCallback(() => {
    if (draftCoordinates.length < 3) return;
    setSelection(createPolygonSelection(draftCoordinates));
    setDraftCoordinates([]);
    setRightPanel(null);
  }, [draftCoordinates]);

  const clearSelection = useCallback(() => {
    setSelection(null);
    setSelectedPlace(null);
    setDraftCoordinates([]);
    setRightPanel((current) => (current === 'polygon' ? null : current));
  }, []);

  const selectPlace = useCallback((place: PlaceDetails) => {
    const nextSelection: PointSelection = {
      kind: 'point',
      longitude: place.longitude,
      latitude: place.latitude,
      zoom: 13,
      features: [{ id: place.id, label: place.name, layer: 'search' }],
    };
    setSelectedPlace(place);
    setIsPlaceDetailsCollapsed(false);
    setSelection(nextSelection);
    setRightPanel(null);
    setMapFocusRequest((current) => ({
      id: (current?.id ?? 0) + 1,
      center: [place.longitude, place.latitude],
      zoom: 13,
    }));
  }, []);

  const handlePointSelect = useCallback(
    (point: PointSelection) => {
      if (Date.now() - lastMapSearchDismissalRef.current < 1_000) {
        lastMapSearchDismissalRef.current = 0;
        return;
      }
      if (isSearchOpen) {
        setIsSearchOpen(false);
        return;
      }
      const namedPlace = point.features.find((feature) => feature.isNamedPlace);
      if (!namedPlace && selectedPlace) {
        setSelection(null);
        setSelectedPlace(null);
        return;
      }
      const name = namedPlace?.label ?? 'Selected location';
      setSelection(point);
      setSelectedPlace({
        id: `map-${point.longitude}-${point.latitude}`,
        name,
        context: namedPlace ? 'Map place' : 'Map coordinates',
        longitude: point.longitude,
        latitude: point.latitude,
        temperatureC: 28,
        weatherLabel: 'Weather unavailable',
      });
      setIsPlaceDetailsCollapsed(false);
    },
    [isSearchOpen, selectedPlace],
  );

  const handleMapPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      if (!isSearchOpen) return;
      const target = event.target;
      if (!(target instanceof Element) || !target.closest('.map-canvas, .map-fallback')) return;
      lastMapSearchDismissalRef.current = Date.now();
      setIsSearchOpen(false);
    },
    [isSearchOpen],
  );

  const handleMapCommand = useCallback((action: MapControlAction) => {
    setMapControlRequest((current) => ({ id: (current?.id ?? 0) + 1, action }));
  }, []);

  const handleStatusChange = useCallback(
    (_ready: boolean, message: string) => setMapStatus(message),
    [],
  );

  const handleBuildingsAvailability = useCallback((available: boolean) => {
    if (!available) setMapStatus('Map ready · 3D building source unavailable');
  }, []);

  const toggleLayers = useCallback(() => {
    if (rightPanel === 'layers') {
      setRightPanel(null);
      return;
    }
    setDraftCoordinates([]);
    setRightPanel('layers');
  }, [rightPanel]);

  const handleDraftCoordinate = useCallback((coordinate: [number, number]) => {
    setDraftCoordinates((current) => [...current, coordinate]);
  }, []);

  const handleOpacityChange = useCallback((layer: UrbanLayerDefinition, opacity: number) => {
    setOpacityByLayer((current) => setLayerOpacity(current, layer.id, opacity));
  }, []);

  const closeRightPanel = useCallback(() => setRightPanel(null), []);
  const togglePlaceDetails = useCallback(
    () => setIsPlaceDetailsCollapsed((current) => !current),
    [],
  );

  return {
    mode,
    mapStyle,
    timeRange,
    layers,
    opacityByLayer,
    selection,
    selectedPlace,
    userLocation,
    draftCoordinates,
    rightPanel,
    isSearchOpen,
    isPlaceDetailsCollapsed,
    mapControlRequest,
    mapFocusRequest,
    mapStatus,
    isDrawing: rightPanel === 'polygon',
    setMapStyle,
    setTimeRange,
    setUserLocation,
    setIsSearchOpen,
    handleModeChange,
    handleLayerToggle,
    startDrawing,
    cancelDrawing,
    completeDrawing,
    clearSelection,
    selectPlace,
    handlePointSelect,
    handleMapPointerDown,
    handleMapCommand,
    handleStatusChange,
    handleBuildingsAvailability,
    toggleLayers,
    handleDraftCoordinate,
    handleOpacityChange,
    closeRightPanel,
    togglePlaceDetails,
  };
}
