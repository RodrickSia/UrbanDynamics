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

export default function App() {
  const configuration = useMemo(
    () => getMapConfiguration(import.meta.env.VITE_GOONG_MAPTILES_KEY),
    [],
  );
  const workspace = useMapWorkspace();
  const backend = useBackendLayers(workspace.layers);
  const zoning = useZoning(backend.catalog.parcels?.available === true);
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
          zoning={{ active: zoning.active, plan: zoning.plan, scenario: zoning.scenario,
            selected: zoning.selected, sketch: zoning.sketch, preview: zoning.preview,
            opacity: zoning.opacity, visible: zoning.visible, showParcels: zoning.showParcels,
            parcelAvailable: zoning.parcelAvailable, busy: zoning.busy,
            onPick: zoning.pick, onSketch: zoning.setSketch, onFinish: () => void zoning.finish(),
            onCancel: zoning.cancel, focus: zoning.focus }}
          backend={{selections:backend.selections,opacity:workspace.opacityByLayer,revision:backend.revision,report:backend.report}}
          viewshed={{state:workspace.viewsheds,onAction:workspace.handleViewshedAction,onStatus:workspace.setViewshedStatus}}
          configuration={configuration}
          mapStyle={workspace.mapStyle}
          mode={workspace.mode}
          buildingsEnabled={Boolean(workspace.layers['buildings-3d'])}
          poiEnabled={workspace.layers.poi ?? true}
          buildingsOpacity={workspace.opacityByLayer['buildings-3d'] ?? 0.8}
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
          onBuildingsAvailabilityChange={workspace.handleBuildingsAvailability}
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

        <ZoningWorkspace workspace={zoning} onActivate={activateZoning}
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
          mode={workspace.mode}
          rightPanelOpen={workspace.rightPanel === 'layers'}
          layersOpen={workspace.rightPanel === 'layers'}
          onModeChange={mode => { if (zoning.busy) return; zoning.close(); workspace.handleModeChange(mode); }}
          onToggleLayers={() => { if (zoning.busy) return; zoning.close(); workspace.toggleLayers(); }}
          onCommand={workspace.handleMapCommand}
        />

        <MapControls
          viewshedActive={workspace.viewsheds.phase !== 'idle'}
          onViewshed={() => { if (zoning.busy) return; zoning.close(); workspace.handleViewshedAction({type:'start'}); }}
          mode={workspace.mode}
          onToggleMeasurementComponents={workspace.toggleMeasurementComponents}
          measurement={workspace.measurement}
          rightPanelOpen={workspace.rightPanel === 'layers'}
          hasSelection={Boolean(workspace.selection)}
          mapStyle={workspace.mapStyle}
          onMapStyleChange={workspace.setMapStyle}
          onStartMeasurement={kind => { if (zoning.busy) return; zoning.close(); workspace.startMeasurement(kind); }}
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
