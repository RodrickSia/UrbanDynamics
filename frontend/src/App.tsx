import { useMemo } from 'react';

import { LayerPanel } from './features/map/components/LayerPanel';
import { MapControls } from './features/map/components/MapControls';
import { MapNavigationControls } from './features/map/components/MapNavigationControls';
import { PlaceDetailsPanel } from './features/map/components/PlaceDetailsPanel';
import { SearchBox } from './features/map/components/SearchBox';
import { UrbanMap } from './features/map/components/UrbanMap';
import { getMapConfiguration } from './features/map/config/mapConfig';
import { useMapWorkspace } from './features/map/hooks/useMapWorkspace';

export default function App() {
  const configuration = useMemo(
    () => getMapConfiguration(import.meta.env.VITE_GOONG_MAPTILES_KEY),
    [],
  );
  const workspace = useMapWorkspace();

  return (
    <main className="app-shell theme-light">
      <section
        className="map-workspace"
        aria-label="Interactive urban map"
        onPointerDownCapture={workspace.handleMapPointerDown}
      >
        <UrbanMap
          configuration={configuration}
          mapStyle={workspace.mapStyle}
          mode={workspace.mode}
          buildingsEnabled={Boolean(workspace.layers['buildings-3d'])}
          buildingsOpacity={workspace.opacityByLayer['buildings-3d'] ?? 0.8}
          isDrawing={workspace.isDrawing}
          draftCoordinates={workspace.draftCoordinates}
          selection={workspace.selection}
          userLocation={workspace.userLocation}
          focusRequest={workspace.mapFocusRequest}
          controlRequest={workspace.mapControlRequest}
          onDraftCoordinate={workspace.handleDraftCoordinate}
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
          />
        </div>

        {workspace.rightPanel === 'layers' && (
          <LayerPanel
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
          onModeChange={workspace.handleModeChange}
          onToggleLayers={workspace.toggleLayers}
          onCommand={workspace.handleMapCommand}
        />

        <MapControls
          isDrawing={workspace.isDrawing}
          rightPanelOpen={workspace.rightPanel === 'layers'}
          draftVertexCount={workspace.draftCoordinates.length}
          hasSelection={Boolean(workspace.selection)}
          mapStyle={workspace.mapStyle}
          timeRange={workspace.timeRange}
          onMapStyleChange={workspace.setMapStyle}
          onTimeRangeChange={workspace.setTimeRange}
          onStartDrawing={workspace.startDrawing}
          onCancelDrawing={workspace.cancelDrawing}
          onCompleteDrawing={workspace.completeDrawing}
          onClearSelection={workspace.clearSelection}
        />

        <div className="sr-only" aria-live="polite">
          {workspace.mapStatus}
        </div>
      </section>
    </main>
  );
}
