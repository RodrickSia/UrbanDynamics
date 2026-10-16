import { useMemo, useState } from 'react';

import { LayerPanel } from './features/map/components/LayerPanel';
import { MapControls } from './features/map/components/MapControls';
import { MapNavigationControls } from './features/map/components/MapNavigationControls';
import { PlaceDetailsPanel } from './features/map/components/PlaceDetailsPanel';
import { SearchBox } from './features/map/components/SearchBox';
import { UrbanMap } from './features/map/components/UrbanMap';
import { getMapConfiguration } from './features/map/config/mapConfig';
import { useMapWorkspace } from './features/map/hooks/useMapWorkspace';
import { ViewshedPanel } from './features/map/viewshed/ViewshedPanel';
import { useBackendLayers } from './features/map/datasets/useBackendLayers';
import { useZoning } from './features/zoning/useZoning';
import { ZoningWorkspace } from './features/zoning/ZoningWorkspace';
import { DevelopmentAssistant } from './features/agent/DevelopmentAssistant';

export default function App() {
  const configuration = useMemo(
    () => getMapConfiguration(import.meta.env.VITE_GOONG_MAPTILES_KEY),
    [],
  );
  const workspace = useMapWorkspace();
  const backend = useBackendLayers(workspace.layers, workspace.mode);
  const [assistantOpen,setAssistantOpen]=useState(false),[assistantBusy,setAssistantBusy]=useState(false);
  const [agentViewport,setAgentViewport]=useState<number[]>();
  const [agentPois,setAgentPois]=useState<import('./features/agent/mapPoi').MapPoiSnapshot>();
  const [agentCandidates,setAgentCandidates]=useState<import('geojson').FeatureCollection>({type:'FeatureCollection',features:[]});
  const zoning = useZoning(backend.catalog.parcels?.available === true,assistantBusy);
  const [searchPanelHeight, setSearchPanelHeight] = useState(0);
  const activateZoning = () => {
    workspace.cancelMeasurement();
    workspace.handleViewshedAction({ type: 'done' });
    workspace.clearSelection();
    workspace.closeRightPanel();
    workspace.setIsSearchOpen(false);
    workspace.handleModeChange('2d');
  };

  return (
    <main className="app-shell theme-light">
      <section
        className="map-workspace"
        data-layers-open={workspace.rightPanel === 'layers'}
        data-zoning-open={zoning.active && !workspace.isSearchOpen}
        data-zoning-plan-open={zoning.active && !!zoning.plan && !workspace.isSearchOpen}
        aria-label="Interactive urban map"
        onPointerDownCapture={workspace.handleMapPointerDown}
      >
        <UrbanMap
          onViewportChange={setAgentViewport} onPoiSnapshot={assistantOpen?setAgentPois:undefined} agentCandidates={assistantOpen?agentCandidates:undefined}
          zoning={{ active: zoning.active, plan: zoning.plan, displayedPlans: zoning.displayedPlans,
            scenario: zoning.analyzing && !zoning.includeScenario ? zoning.plan?.scenarios[0] ?? null : zoning.scenario,
            analysis: { active: zoning.analyzing, geometry: zoning.analysisArea, chart: zoning.indicatorChart },
            selected: zoning.selected, sketch: zoning.sketch, preview: zoning.preview,
            opacity: zoning.opacity, visible: zoning.visible, showParcels: zoning.showParcels,
            parcelAvailable: zoning.parcelAvailable, busy: zoning.busy,
            onPick: zoning.pick, onSketch: zoning.setSketch, onFinish: () => void zoning.finish(),
            onCancel: zoning.cancel, focus: zoning.focus,
            development: { active: !zoning.analyzing && zoning.section === 'development', parcel: zoning.development.parcel,
              selectedBuilding: zoning.development.selectedBuilding, preview: zoning.development.preview?.building ?? null,
              onPickParcel: zoning.development.pickParcel, onPickBuilding: zoning.development.pickBuilding,
              onBaseline: zoning.development.onBaseline,
              onDelete: () => { if (!zoning.readOnly && !zoning.busy && !zoning.development.dirty && zoning.development.selectedBuilding) zoning.development.setDeleteRequested(true); },
              onUndo: redo => { if (!zoning.readOnly && !zoning.busy && !zoning.development.dirty) void zoning.execute(redo ? 'redo_development' : 'undo_development'); } } }}
          backend={{selections:backend.selections,opacity:workspace.opacityByLayer,revision:backend.revision,report:backend.report}}
          viewshed={{state:workspace.viewsheds,onAction:workspace.handleViewshedAction,onStatus:workspace.setViewshedStatus}}
          configuration={configuration}
          mapStyle={workspace.mapStyle}
          mode={workspace.mode}
          buildingsOpacity={workspace.opacityByLayer['buildings-3d'] ?? 0.8}
          poiEnabled={workspace.layers.poi ?? true}
          landPriceEnabled={Boolean(workspace.layers['land-price'])}
          landPriceOpacity={workspace.opacityByLayer['land-price'] ?? 0.8}
          measurement={workspace.measurement}
          selection={workspace.selection}
          userLocation={workspace.userLocation}
          focusRequest={workspace.mapFocusRequest}
          controlRequest={workspace.mapControlRequest}
          onMeasurementPoint={workspace.handleMeasurementPoint}
          onMeasurementPreview={workspace.handleMeasurementPreview}
          onMeasurementPointsChange={workspace.handleMeasurementPointsChange}
          onPointSelect={workspace.handlePointSelect}
          onUserLocationChange={workspace.setUserLocation}
          onStatusChange={workspace.handleStatusChange}
        />

        {workspace.selectedPlace && (
          <PlaceDetailsPanel
            place={workspace.selectedPlace}
            isCollapsed={workspace.isPlaceDetailsCollapsed}
            onToggleCollapsed={workspace.togglePlaceDetails}
            onClose={workspace.clearSelection}
          />
        )}

        <div className="search-dock">
          <SearchBox
            isOpen={workspace.isSearchOpen}
            onOpenChange={workspace.setIsSearchOpen}
            onSelectPlace={workspace.selectPlace}
            onWorkspaceHeightChange={setSearchPanelHeight}
          />
        </div>

        <ZoningWorkspace workspace={zoning} onActivate={activateZoning} onView={workspace.handleModeChange} viewMode={workspace.mode}
          searchOpen={workspace.isSearchOpen} searchPanelHeight={searchPanelHeight}/>

        {workspace.rightPanel === 'layers' && (
          <LayerPanel
            backend={backend}
            layers={workspace.layers}
            opacityByLayer={workspace.opacityByLayer}
            onClose={workspace.closeRightPanel}
            onToggleLayer={workspace.handleLayerToggle}
            onOpacityChange={workspace.handleOpacityChange}
          />
        )}

        <MapNavigationControls
          assistantOpen={assistantOpen}
          onToggleAssistant={()=>{if(!assistantBusy){setAssistantOpen(!assistantOpen);workspace.closeRightPanel();}}}
          mode={workspace.mode}
          rightPanelOpen={workspace.rightPanel === 'layers'}
          layersOpen={workspace.rightPanel === 'layers'}
          onModeChange={mode => { if (zoning.busy) return; workspace.handleModeChange(mode); }}
          onToggleLayers={() => zoning.close(workspace.toggleLayers)}
          onCommand={workspace.handleMapCommand}
        />

        {assistantOpen&&<DevelopmentAssistant workspace={zoning} onBusy={setAssistantBusy} onClose={()=>setAssistantOpen(false)}
          viewport={agentViewport} mapPois={agentPois} onCandidates={setAgentCandidates} selectedPlace={workspace.selectedPlace}
          onMapAction={action=>{
            const notes:string[]=[];
            if(action.type==='focus'&&action.bbox)workspace.focusBounds(action.bbox);
            if(action.type==='layers')for(const id of action.layer_ids??[]){
              const layer=backend.definitions.find(l=>l.id===id);
              if(!layer||layer.status!=='available'){notes.push(`${layer?.label??id}: source unavailable; layer was not enabled.`);continue;}
              if(!workspace.layers[layer.id])workspace.handleLayerToggle(layer);
            }
            return notes;
          }}/ >}

        <MapControls
          viewshedActive={workspace.viewsheds.phase !== 'idle'}
          onViewshed={() => zoning.close(() => workspace.handleViewshedAction({type:'start'}))}
          mode={workspace.mode}
          onToggleMeasurementComponents={workspace.toggleMeasurementComponents}
          measurement={workspace.measurement}
          rightPanelOpen={workspace.rightPanel === 'layers'}
          hasSelection={Boolean(workspace.selection)}
          mapStyle={workspace.mapStyle}
          onMapStyleChange={workspace.setMapStyle}
          onStartMeasurement={kind => zoning.close(() => workspace.startMeasurement(kind))}
          onMeasurementUnitsChange={workspace.changeMeasurementUnits}
          onUndoMeasurementPoint={workspace.undoMeasurementPoint}
          onCancelMeasurement={workspace.cancelMeasurement}
          onCompleteMeasurement={workspace.completeMeasurement}
          onClearSelection={workspace.clearSelection}
        />

        {workspace.viewsheds.phase !== 'idle' && <ViewshedPanel state={workspace.viewsheds}
          onAction={workspace.handleViewshedAction} status={workspace.mode==='3d'?workspace.viewshedStatus:'Switch to 3D to see this analysis'}/>}

        <div className="sr-only" aria-live="polite">
          {workspace.mapStatus}
        </div>
      </section>
    </main>
  );
}
