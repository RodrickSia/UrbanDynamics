import type { Position } from 'geojson';

import type { MapConfiguration, MapStyleId } from '../config/mapConfig';
import type {
  MapControlRequest,
  MapFocusRequest,
  MapMode,
  MapSelection,
  PointSelection,
  UserLocation,
} from '../types/map';

export interface UrbanMapProps {
  configuration: MapConfiguration;
  mapStyle: MapStyleId;
  mode: MapMode;
  buildingsEnabled: boolean;
  buildingsOpacity: number;
  isDrawing: boolean;
  draftCoordinates: Position[];
  selection: MapSelection;
  userLocation: UserLocation | null;
  focusRequest: MapFocusRequest | null;
  controlRequest: MapControlRequest | null;
  onDraftCoordinate: (coordinate: [number, number]) => void;
  onPointSelect: (selection: PointSelection) => void;
  onUserLocationChange: (location: UserLocation) => void;
  onStatusChange: (ready: boolean, message: string) => void;
  onBuildingsAvailabilityChange: (available: boolean) => void;
}
