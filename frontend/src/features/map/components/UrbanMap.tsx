import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { DEFAULT_VIEWPORT, getMapStyle } from '../config/mapConfig';
import { configureMapLibreWorker } from '../config/maplibreWorker';
import { configureSceneLod, MAP_CACHE_BUDGET } from '../config/renderBudget';
import { useLocationMarkers } from '../hooks/useLocationMarkers';
import { useMapCommands } from '../hooks/useMapCommands';
import { setBuildings3d } from '../layers/buildings3d';
import {
  createMeasurementLayer,
  MEASUREMENT_LAYER_ID,
  type MeasurementLayer,
} from '../layers/measurementLayer';
import { setTerrain } from '../layers/terrain';
import { installMetricRoadWidths } from '../layers/metricRoadWidths';
import { createMapInteractionHandlers } from '../utils/mapInteractions';
import { MeasurementLabels } from './MeasurementLabels';
import type { UrbanMapProps } from './UrbanMap.types';
import { ViewshedScene } from '../viewshed/ViewshedScene';
import { createPoiVisibility } from '../layers/poi';
import { BackendDataScene } from '../datasets/BackendDataScene';

export function UrbanMap(props: UrbanMapProps) {
  const {
    configuration,
    mapStyle,
    mode,
    buildingsEnabled,
    buildingsOpacity,
    measurement,
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
  const measurementLayerRef = useRef<MeasurementLayer | null>(null);
  const propsRef = useRef(props);
  const poiVisibility = useRef(createPoiVisibility());
  const styleRef = useRef(mapStyle);
  const styleReadyRef = useRef(false);
  const cameraModeRef = useRef('2d');
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
    let disposeInteractions: () => void = () => undefined;
    let disposeRoadWidths: () => void = () => undefined;
    styleReadyRef.current = false;

    void import('maplibre-gl')
      .then((maplibregl) => {
        if (disposed || !containerRef.current) return;
        configureMapLibreWorker(maplibregl);
        const initialStyle = propsRef.current.mapStyle;
        styleRef.current = initialStyle;
        const map = new maplibregl.Map({
          ...MAP_CACHE_BUDGET,
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
        cameraModeRef.current = '2d';
        mapRef.current = map;
        markerConstructorRef.current = maplibregl.Marker;
        const measurementLayer = createMeasurementLayer(maplibregl.MercatorCoordinate);
        measurementLayerRef.current = measurementLayer;
        setMapRevision((revision) => revision + 1);

        map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-left');

        const applyMode = () => {
          const current = propsRef.current;
          const in3d = current.mode === '3d';
          try {
            // Insert terrain first so its hillshade stays below building extrusions.
            setTerrain(map, in3d);
          } catch {
            if (in3d) current.onStatusChange(true, 'Map ready · 3D terrain unavailable');
          }
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
        };

        const handleStyleLoad = () => {
          disposeRoadWidths();
          styleReadyRef.current = true;
          configureSceneLod(map);
          disposeRoadWidths = installMetricRoadWidths(map);
          poiVisibility.current(map, propsRef.current.poiEnabled ?? true, true);
          applyMode();
          if (!map.getLayer(MEASUREMENT_LAYER_ID)) map.addLayer(measurementLayer);
          // Custom layers survive style diffing but newly added raster/style
          // layers are appended above them. Always restore the overlay order.
          map.moveLayer(MEASUREMENT_LAYER_ID);
          measurementLayer.setMeasurement(
            propsRef.current.measurement,
            propsRef.current.mode,
          );
          propsRef.current.onStatusChange(true, 'Goong map is ready');
          setMapRevision((revision) => revision + 1);
        };

        const interactions = createMapInteractionHandlers(map, () => propsRef.current, measurementLayer.projection);
        disposeInteractions = interactions.dispose;

        map.on('style.load', handleStyleLoad);
        map.on('click', interactions.click);
        map.on('mousemove', interactions.mousemove);
        map.on('mouseout', interactions.mouseout);
        map.on('movestart', interactions.movestart);
        map.on('idle', interactions.idle);
        map.on('sourcedata', interactions.scenechange);
        map.on('styledata', interactions.scenechange);
        map.on('error', () =>
          propsRef.current.onStatusChange(false, 'Some map data could not be loaded'),
        );
      })
      .catch(() => propsRef.current.onStatusChange(false, 'MapLibre could not be initialized'));

    return () => {
      disposed = true;
      disposeInteractions();
      disposeRoadWidths();
      styleReadyRef.current = false;
      markerConstructorRef.current = null;
      measurementLayerRef.current = null;
      mountedMap?.remove();
      if (mapRef.current === mountedMap) mapRef.current = null;
    };
  }, [configuration]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !configuration.ok || styleRef.current === mapStyle) return;
    styleRef.current = mapStyle;
    styleReadyRef.current = false;
    onStatusChange(false, 'Changing basemap…');
    map.setStyle(getMapStyle(configuration.mapKey, mapStyle));
  }, [configuration, mapStyle, onStatusChange]);

  useEffect(() => {
    if (mapRef.current && styleReadyRef.current)
      poiVisibility.current(mapRef.current, props.poiEnabled ?? true);
  }, [props.poiEnabled, mapRevision]);

  useEffect(() => {
    const map = mapRef.current;
    // isStyleLoaded also becomes false while tiles load during camera movement.
    // Style metadata is enough to apply a user's mode change.
    if (!map || !styleReadyRef.current || !configuration.ok) return;
    const in3d = mode === '3d';
    try {
      setTerrain(map, in3d);
    } catch {
      if (in3d) onStatusChange(true, 'Map ready · 3D terrain unavailable');
    }
    try {
      const available = setBuildings3d(map, in3d && buildingsEnabled, buildingsOpacity);
      onBuildingsAvailabilityChange(available);
    } catch {
      onBuildingsAvailabilityChange(false);
    }
    if (map.getLayer(MEASUREMENT_LAYER_ID)) map.moveLayer(MEASUREMENT_LAYER_ID);
  }, [
    buildingsEnabled,
    buildingsOpacity,
    configuration,
    mode,
    mapRevision,
    onBuildingsAvailabilityChange,
    onStatusChange,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current || cameraModeRef.current === mode) return;
    // Allow the new terrain/extrusion pipeline to render before beginning the
    // flight. Opacity, tile loading and basemap changes must not restart it.
    const fly = () => {
      cameraModeRef.current = mode;
      map.easeTo({ pitch: mode === '3d' ? 60 : 0, duration: 800 });
    };
    map.once('render', fly);
    map.triggerRepaint();
    return () => { map.off('render', fly); };
  }, [mode, mapRevision]);

  useEffect(() => {
    const map = mapRef.current;
    const measurementLayer = measurementLayerRef.current;
    if (!map || !measurementLayer) return;
    // Retain every state update even while terrain/vector tiles are loading.
    measurementLayer.setMeasurement(measurement, mode);
    // Layer creation/order belongs to style.load; adding while a style swap
    // is in progress can attach to the outgoing style instead.
    map.getCanvas().classList.toggle('is-measuring', measurement.status === 'active');
  }, [measurement, mode]);

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

  return (
    <>
      <div ref={containerRef} className="map-canvas" aria-label="Interactive map of Vietnam" />
      {props.backend && <BackendDataScene map={mapRef.current} bridge={props.backend}
        interactive={measurement.status!=='active' && (!props.viewshed || props.viewshed.state.phase==='idle')}/>}
      {props.viewshed && <ViewshedScene map={mapRef.current} projection={measurementLayerRef.current?.projection ?? null}
        mode={mode} bridge={props.viewshed} />}
      <MeasurementLabels
        map={mapRef.current}
        projection={measurementLayerRef.current?.projection ?? null}
        measurement={measurement}
        mode={mode}
      />
    </>
  );
}
