import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { DEFAULT_VIEWPORT, getMapStyle } from '../config/mapConfig';
import { configureMapLibreWorker } from '../config/maplibreWorker';
import { useLocationMarkers } from '../hooks/useLocationMarkers';
import { useMapCommands } from '../hooks/useMapCommands';
import { setBuildings3d } from '../layers/buildings3d';
import { ensureSelectionLayers, updateSelectionLayers } from '../layers/selectionLayers';
import { setTerrain } from '../layers/terrain';
import type { UrbanMapProps } from './UrbanMap.types';

export function UrbanMap(props: UrbanMapProps) {
  const {
    configuration,
    mapStyle,
    mode,
    buildingsEnabled,
    buildingsOpacity,
    isDrawing,
    draftCoordinates,
    selection,
    userLocation,
    focusRequest,
    controlRequest,
    onStatusChange,
    onBuildingsAvailabilityChange,
  } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerConstructorRef = useRef<typeof import('maplibre-gl').Marker | null>(null);
  const propsRef = useRef(props);
  const styleRef = useRef(mapStyle);
  const [mapRevision, setMapRevision] = useState(0);
  propsRef.current = props;

  useLocationMarkers(mapRef, markerConstructorRef, mapRevision, selection, userLocation);
  useMapCommands({
    mapRef,
    focusRequest,
    controlRequest,
    onStatusChange,
    onUserLocationChange: props.onUserLocationChange,
  });

  useEffect(() => {
    if (!containerRef.current || !configuration.ok) return;
    const { mapKey } = configuration;
    let disposed = false;
    let mountedMap: MapLibreMap | null = null;

    void import('maplibre-gl')
      .then((maplibregl) => {
        if (disposed || !containerRef.current) return;
        configureMapLibreWorker(maplibregl);
        const initialStyle = propsRef.current.mapStyle;
        styleRef.current = initialStyle;
        const map = new maplibregl.Map({
          container: containerRef.current,
          style: getMapStyle(mapKey, initialStyle),
          center: DEFAULT_VIEWPORT.center,
          zoom: DEFAULT_VIEWPORT.zoom,
          pitch: DEFAULT_VIEWPORT.pitch,
          bearing: DEFAULT_VIEWPORT.bearing,
          canvasContextAttributes: { antialias: true },
          attributionControl: false,
        });
        mountedMap = map;
        mapRef.current = map;
        markerConstructorRef.current = maplibregl.Marker;
        setMapRevision((revision) => revision + 1);

        map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-left');

        const applyMode = () => {
          const current = propsRef.current;
          const in3d = current.mode === '3d';
          let buildingsAvailable = true;
          try {
            buildingsAvailable = setBuildings3d(
              map,
              in3d && current.buildingsEnabled,
              current.buildingsOpacity,
            );
          } catch {
            buildingsAvailable = false;
          }
          current.onBuildingsAvailabilityChange(buildingsAvailable);
          try {
            setTerrain(map, mapKey, in3d);
          } catch {
            current.onStatusChange(true, 'Map ready · 3D terrain unavailable');
          }
          map.easeTo({ pitch: in3d ? 48 : 0, bearing: 0, duration: 600 });
        };

        const handleStyleLoad = () => {
          ensureSelectionLayers(map);
          updateSelectionLayers(map, propsRef.current.draftCoordinates, propsRef.current.selection);
          applyMode();
          propsRef.current.onStatusChange(true, 'Goong map is ready');
        };

        const handleClick = (event: MapMouseEvent) => {
          const current = propsRef.current;
          if (current.isDrawing) {
            current.onDraftCoordinate([event.lngLat.lng, event.lngLat.lat]);
            return;
          }
          const visibleFeatures = map
            .queryRenderedFeatures(event.point)
            .filter((feature) => !feature.layer.id.startsWith('urban-selection'))
            .slice(0, 5)
            .map((feature, index) => {
              const featureName = feature.properties?.name;
              const isNamedPlace = typeof featureName === 'string' && featureName.trim().length > 0;
              return {
                id: String(feature.id ?? `${feature.layer.id}-${index}`),
                label: String(featureName ?? feature.properties?.class ?? feature.layer.id),
                layer: feature.layer.id,
                isNamedPlace,
              };
            });
          current.onPointSelect({
            kind: 'point',
            longitude: event.lngLat.lng,
            latitude: event.lngLat.lat,
            zoom: map.getZoom(),
            features: visibleFeatures,
          });
        };

        map.on('style.load', handleStyleLoad);
        map.on('click', handleClick);
        map.on('error', () =>
          propsRef.current.onStatusChange(false, 'Some map data could not be loaded'),
        );
      })
      .catch(() => propsRef.current.onStatusChange(false, 'MapLibre could not be initialized'));

    return () => {
      disposed = true;
      markerConstructorRef.current = null;
      mountedMap?.remove();
      if (mapRef.current === mountedMap) mapRef.current = null;
    };
  }, [configuration]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !configuration.ok || styleRef.current === mapStyle) return;
    styleRef.current = mapStyle;
    onStatusChange(false, 'Changing basemap…');
    map.setStyle(getMapStyle(configuration.mapKey, mapStyle));
  }, [configuration, mapStyle, onStatusChange]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded() || !configuration.ok) return;
    const in3d = mode === '3d';
    try {
      const available = setBuildings3d(map, in3d && buildingsEnabled, buildingsOpacity);
      onBuildingsAvailabilityChange(available);
      setTerrain(map, configuration.mapKey, in3d);
    } catch {
      onBuildingsAvailabilityChange(false);
    }
    map.easeTo({ pitch: in3d ? 48 : 0, bearing: 0, duration: 600 });
  }, [
    buildingsEnabled,
    buildingsOpacity,
    configuration,
    mode,
    onBuildingsAvailabilityChange,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    ensureSelectionLayers(map);
    updateSelectionLayers(map, draftCoordinates, selection);
    map.getCanvas().classList.toggle('is-drawing', isDrawing);
  }, [draftCoordinates, isDrawing, selection]);

  if (!configuration.ok) {
    return (
      <div className="map-fallback" role="alert">
        <div className="fallback-grid" aria-hidden="true" />
        <div className="fallback-message">
          <strong>Map could not be initialized</strong>
          <p>{configuration.message}</p>
        </div>
      </div>
    );
  }

  return <div ref={containerRef} className="map-canvas" aria-label="Interactive map of Vietnam" />;
}
