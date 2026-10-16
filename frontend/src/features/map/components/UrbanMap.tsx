import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import { DEFAULT_VIEWPORT, getMapStyle, getFallbackMapStyle } from '../config/mapConfig';
import { configureMapLibreWorker } from '../config/maplibreWorker';
import { configureSceneLod, MAP_CACHE_BUDGET } from '../config/renderBudget';
import { useLocationMarkers } from '../hooks/useLocationMarkers';
import { useMapCommands } from '../hooks/useMapCommands';
import { setBuildings3d } from '../layers/buildings3d';
import { installLandPrice, LAND_PRICE_LAYER, type LandPriceStatus, type LandPriceProperties } from '../layers/landPrice';
import { LandPriceLegend } from './LandPriceLegend';
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
import { mapPoiSnapshot } from '../../agent/mapPoi';
import { BackendDataScene } from '../datasets/BackendDataScene';
import { ZoningScene } from '../../zoning/ZoningScene';
import { DisplayedPlanParcelsScene } from '../../zoning/DisplayedPlanParcelsScene';
import { DevelopmentScene } from '../../zoning/DevelopmentScene';
import { PlanBuildingsScene } from '../../zoning/PlanBuildingsScene';
import { IndicatorChartScene } from '../../zoning/IndicatorChartScene';
import { ZoningLabels } from '../../zoning/ZoningLabels';

export function UrbanMap(props: UrbanMapProps) {
  const {
    configuration,
    mapStyle,
    mode,
    buildingsOpacity = 0.8,
    landPriceEnabled = false,
    landPriceOpacity = 0.8,
    measurement,
    selection,
    userLocation,
    focusRequest,
    controlRequest,
    onStatusChange,
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
  const fallbackActive=useRef(false);
  const [fallbackReason,setFallbackReason]=useState('');
  const [landPriceStatus, setLandPriceStatus] = useState<LandPriceStatus>({ state: 'loading' });
  const [landPriceSelection, setLandPriceSelection] = useState<LandPriceProperties | null>(null);
  const [priceRetry, setPriceRetry] = useState(0);
  propsRef.current = props;

  useLocationMarkers(mapRef, markerConstructorRef, mapRevision, selection, userLocation);
  useMapCommands({
    readyRevision:mapRevision,
    mapRef,
    focusRequest,
    controlRequest,
    onStatusChange,
    onUserLocationChange: props.onUserLocationChange,
  });

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current || !landPriceEnabled) return;
    return installLandPrice(map, propsRef.current.landPriceOpacity ?? 0.8, setLandPriceStatus,
      properties => {
        const current = propsRef.current;
        if (properties === null || (!current.zoning?.active && current.measurement.status !== 'active' &&
          (!current.viewshed || current.viewshed.state.phase === 'idle'))) setLandPriceSelection(properties);
      });
  }, [landPriceEnabled, mapRevision, priceRetry]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer(LAND_PRICE_LAYER)) map.setPaintProperty(LAND_PRICE_LAYER, 'line-opacity', landPriceOpacity);
  }, [landPriceOpacity, mapRevision, landPriceStatus.state]);


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
        fallbackActive.current=false;setFallbackReason('');
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
        map.addControl(new maplibregl.AttributionControl({compact:true}), 'bottom-right');

        const applyMode = () => {
          const current = propsRef.current;
          const in3d = current.mode === '3d';
          try {
            // Insert terrain first so its hillshade stays below building extrusions.
            setTerrain(map, in3d);
          } catch {
            if (in3d) current.onStatusChange(true, 'Map ready · 3D terrain unavailable');
          }
          try { setBuildings3d(map, in3d, current.buildingsOpacity ?? 0.8); }
          catch { current.onStatusChange(true, 'Map ready · Goong buildings unavailable'); }
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
          propsRef.current.onStatusChange(true, fallbackActive.current?'Map ready · alternate basemap':'Map ready');
          { const b=map.getBounds(); propsRef.current.onViewportChange?.([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]); }
          setMapRevision((revision) => revision + 1);
        };

        const interactions = createMapInteractionHandlers(map, () => propsRef.current, measurementLayer.projection);
        disposeInteractions = interactions.dispose;

        map.on('style.load', handleStyleLoad);
        map.on('click', interactions.click);
        map.on('mousemove', interactions.mousemove);
        map.on('mouseout', interactions.mouseout);
        map.on('movestart', interactions.movestart);
        map.on('moveend',()=>{const b=map.getBounds();propsRef.current.onViewportChange?.([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);});
        map.on('idle', interactions.idle);
        map.on('sourcedata', interactions.scenechange);
        map.on('styledata', interactions.scenechange);
        map.on('error', event => {
          const error=event.error as Error&{status?:number;url?:string};
          const goong=String(error.url??error.message??'').includes('goong.io');
          if(goong&&fallbackActive.current)return; // Ignore cancelled outgoing provider requests.
          if(goong&&!fallbackActive.current&&([401,403,429,500,502,503,504].includes(error.status??0))){
            fallbackActive.current=true;
            setFallbackReason(error.status===429?'Goong is rate-limited. Showing OpenStreetMap instead.':'Goong is unavailable. Showing OpenStreetMap instead.');
            styleReadyRef.current=false;
            propsRef.current.onStatusChange(false,'Loading alternate basemap…');
            map.setStyle(getFallbackMapStyle());
            return;
          }
          propsRef.current.onStatusChange(false,'Some map data could not be loaded');
        });
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
    fallbackActive.current=false;setFallbackReason('');
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
    try { setBuildings3d(map, in3d, buildingsOpacity); }
    catch { onStatusChange(true, 'Map ready · Goong buildings unavailable'); }
    if (map.getLayer(MEASUREMENT_LAYER_ID)) map.moveLayer(MEASUREMENT_LAYER_ID);
  }, [
    configuration,
    mode,
    mapRevision,
    buildingsOpacity,
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

  useEffect(()=>{
    const map=mapRef.current;
    if(!map||!styleReadyRef.current)return;
    const id='urban-agent-candidates';
    const data=props.agentCandidates??{type:'FeatureCollection' as const,features:[]};
    if(!map.getSource(id))map.addSource(id,{type:'geojson',data});
    else (map.getSource(id) as import('maplibre-gl').GeoJSONSource).setData(data);
    if(!map.getLayer(id+'-fill'))map.addLayer({id:id+'-fill',type:'fill',source:id,filter:['==',['geometry-type'],'Polygon'],paint:{'fill-color':'#d7791f','fill-opacity':.22}});
    if(!map.getLayer(id+'-line'))map.addLayer({id:id+'-line',type:'line',source:id,paint:{'line-color':['case',['==',['get','source'],'Goong Directions V2'],'#1d4ed8','#bd6415'],'line-width':['case',['==',['get','source'],'Goong Directions V2'],5,3]}});
    if(!map.getLayer(id+'-points'))map.addLayer({id:id+'-points',type:'circle',source:id,filter:['==',['geometry-type'],'Point'],paint:{'circle-radius':6,'circle-color':'#d7791f','circle-stroke-color':'white','circle-stroke-width':2}});
    if(!map.getLayer(id+'-labels'))map.addLayer({id:id+'-labels',type:'symbol',source:id,filter:['==',['geometry-type'],'Polygon'],layout:{'text-field':['to-string',['get','parcel_id']],'text-size':12},paint:{'text-color':'#773d0b','text-halo-color':'white','text-halo-width':1.5}});
  },[props.agentCandidates,mapRevision]);

  useEffect(()=>{
    const map=mapRef.current,callback=props.onPoiSnapshot;
    if(!map||!styleReadyRef.current||!callback)return;
    let previous='';
    const publish=()=>{
      try{
        const snapshot=mapPoiSnapshot(map);
        const signature=JSON.stringify([snapshot.bbox,snapshot.zoom,snapshot.features]);
        if(signature!==previous){previous=signature;callback(snapshot);}
      }catch{/* A style switch temporarily removes source layers. Retry at idle. */}
    };
    publish();map.on('idle',publish);
    return ()=>{map.off('idle',publish);};
  },[props.onPoiSnapshot,mapRevision]);

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
      {fallbackReason&&<div role="status" style={{position:'absolute',bottom:28,left:'50%',transform:'translateX(-50%)',zIndex:8,
        maxWidth:'min(460px,75%)',padding:'8px 12px',borderRadius:8,background:'#fff8e7',border:'1px solid #dfc78c',
        color:'#604510',fontSize:12,pointerEvents:'none'}}>{fallbackReason} Data layers and the assistant remain available.</div>}
      {props.backend && <BackendDataScene map={mapRef.current} bridge={{ ...props.backend,
        selections: props.backend.selections.filter(selection => selection.id !== 'land-price' &&
          !(props.zoning?.active && selection.id === 'parcels')) }}
        interactive={!props.zoning?.active && measurement.status!=='active' && (!props.viewshed || props.viewshed.state.phase==='idle')}/>}
      {props.zoning && <ZoningScene map={mapRef.current} bridge={props.zoning}/>}
      {props.zoning && <DisplayedPlanParcelsScene map={mapRef.current} bridge={props.zoning}/>}
      {props.zoning && <DevelopmentScene map={mapRef.current} bridge={props.zoning} mode={mode}/>}
      {props.zoning && <PlanBuildingsScene map={mapRef.current} bridge={props.zoning} mode={mode}/>}
      {props.zoning && <IndicatorChartScene map={mapRef.current} bridge={props.zoning} mode={mode}/>}
      {props.zoning && <ZoningLabels map={mapRef.current} bridge={props.zoning}/>}
      {props.viewshed && <ViewshedScene map={mapRef.current} projection={measurementLayerRef.current?.projection ?? null}
        mode={mode} bridge={props.viewshed} />}
      <MeasurementLabels
        map={mapRef.current}
        projection={measurementLayerRef.current?.projection ?? null}
        measurement={measurement}
        mode={mode}
      />
      {landPriceEnabled && !props.zoning?.active && <LandPriceLegend status={landPriceStatus} selected={landPriceSelection}
        onClose={() => setLandPriceSelection(null)} onRetry={() => setPriceRetry(value => value + 1)} />}
    </>
  );
}
