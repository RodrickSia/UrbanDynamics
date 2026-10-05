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
  MeasurementPoint,
  MeasurementKind,
  MeasurementState,
  PlaceDetails,
  PointSelection,
  TimeRange,
  UrbanLayerDefinition,
  UserLocation,
} from '../types/map';
import { calculateAreaMeasurement } from '../utils/measurementArea';
import type { MeasurementUnits } from '../utils/measurementUnits';

export type RightPanel = 'layers' | null;

const EMPTY_MEASUREMENT: MeasurementState = {
  status: 'idle',
  points: [],
  preview: null,
};

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
  const [measurement, setMeasurement] = useState<MeasurementState>(EMPTY_MEASUREMENT);
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

  const startMeasurement = useCallback((kind?: MeasurementKind) => {
    setIsSearchOpen(false);
    setSelectedPlace(null);
    setSelection(null);
    setRightPanel(null);
    setMeasurement(current => ({ status: 'active', points: [], preview: null,
      kind: kind ?? current.kind ?? 'distance', units: current.units ?? 'metric' }));
  }, []);

  const cancelMeasurement = useCallback(() => {
    setMeasurement(EMPTY_MEASUREMENT);
  }, []);

  const toggleMeasurementComponents = useCallback(() => {
    setMeasurement(current => ({ ...current, showComponents: !current.showComponents }));
  }, []);

  const changeMeasurementUnits = useCallback((units: MeasurementUnits) => {
    setMeasurement(current => ({ ...current, units }));
  }, []);

  const undoMeasurementPoint = useCallback(() => {
    setMeasurement(current => ({ ...current, status:'active', points:current.points.slice(0,-1), preview:null }));
  }, []);

  const completeMeasurement = useCallback(() => {
    setMeasurement((current) => (
      (current.kind === 'area' ? !calculateAreaMeasurement(current.points,mode).valid : current.points.length < 2)
        ? current
        : { ...current, status: 'complete', preview: null }
    ));
  }, [mode]);

  const handleMeasurementPoint = useCallback((point: MeasurementPoint) => {
    setMeasurement((current) => (
      current.status !== 'active' || (current.kind === 'area' && current.points.length >= 256)
        ? current
        : { ...current, points: [...current.points, point], preview: null }
    ));
  }, []);

  const handleMeasurementPreview = useCallback((point: MeasurementPoint | null) => {
    setMeasurement((current) => (
      current.status !== 'active' || current.preview === point
        ? current
        : { ...current, preview: point }
    ));
  }, []);

  const handleMeasurementPointsChange = useCallback((points: MeasurementPoint[]) => {
    setMeasurement((current) => ({ ...current, points }));
  }, []);

  const clearSelection = useCallback(() => {
    setSelection(null);
    setSelectedPlace(null);
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
    setRightPanel('layers');
  }, [rightPanel]);

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
    measurement,
    rightPanel,
    isSearchOpen,
    isPlaceDetailsCollapsed,
    mapControlRequest,
    mapFocusRequest,
    mapStatus,
    isMeasuring: measurement.status !== 'idle',
    setMapStyle,
    setTimeRange,
    setUserLocation,
    setIsSearchOpen,
    handleModeChange,
    handleLayerToggle,
    startMeasurement,
    cancelMeasurement,
    completeMeasurement,
    toggleMeasurementComponents,
    changeMeasurementUnits,
    undoMeasurementPoint,
    handleMeasurementPoint,
    handleMeasurementPreview,
    handleMeasurementPointsChange,
    clearSelection,
    selectPlace,
    handlePointSelect,
    handleMapPointerDown,
    handleMapCommand,
    handleStatusChange,
    handleBuildingsAvailability,
    toggleLayers,
    handleOpacityChange,
    closeRightPanel,
    togglePlaceDetails,
  };
}
