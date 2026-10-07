import type { MapConfiguration, MapStyleId } from '../config/mapConfig';
import type {
  MapControlRequest,
  MapFocusRequest,
  MapMode,
  MapSelection,
  MeasurementPoint,
  MeasurementState,
  PointSelection,
  UserLocation,
} from '../types/map';

export interface UrbanMapProps {
  configuration: MapConfiguration;
  mapStyle: MapStyleId;
  mode: MapMode;
  buildingsEnabled: boolean;
  buildingsOpacity: number;
  measurement: MeasurementState;
  selection: MapSelection;
  userLocation: UserLocation | null;
  focusRequest: MapFocusRequest | null;
  controlRequest: MapControlRequest | null;
  onMeasurementPoint: (point: MeasurementPoint) => void;
  onMeasurementPreview: (point: MeasurementPoint | null) => void;
  onMeasurementPointsChange: (points: MeasurementPoint[]) => void;
  onPointSelect: (selection: PointSelection) => void;
  onUserLocationChange: (location: UserLocation) => void;
  onStatusChange: (ready: boolean, message: string) => void;
  onBuildingsAvailabilityChange: (available: boolean) => void;
}
