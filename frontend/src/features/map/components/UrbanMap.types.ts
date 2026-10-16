import type { MapConfiguration, MapStyleId } from '../config/mapConfig';
import type { ViewshedBridge } from '../viewshed/ViewshedScene';
import type { BackendBridge } from '../datasets/BackendDataScene';
import type { ZoningBridge } from '../../zoning/types';
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
  onPoiSnapshot?: (snapshot:import('../../agent/mapPoi').MapPoiSnapshot)=>void;
  onViewportChange?: (bounds: number[]) => void;
  agentCandidates?: import('geojson').FeatureCollection;
  zoning?: ZoningBridge;
  backend?: BackendBridge;
  poiEnabled?: boolean;
  viewshed?: ViewshedBridge;
  configuration: MapConfiguration;
  mapStyle: MapStyleId;
  mode: MapMode;
  buildingsOpacity?: number;
  landPriceEnabled?: boolean;
  landPriceOpacity?: number;
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
}
