export type MapMode = '2d' | '3d';
export type MapControlAction = 'zoom-in' | 'zoom-out' | 'locate';

export interface MapControlRequest {
  id: number;
  action: MapControlAction;
}

export interface MapFocusRequest {
  id: number;
  center: [number, number];
  zoom: number;
}

export interface UserLocation {
  longitude: number;
  latitude: number;
}

export type MeasurementSurface = 'terrain' | 'building' | 'ground';
export type MeasurementStatus = 'idle' | 'active' | 'complete';
export type MeasurementKind = 'distance' | 'area';

/** Geographic positions, altitude in metres; never screen coordinates. */
export interface MeasurementEdge {
  id: string;
  objectId: string;
  start: [number, number, number];
  end: [number, number, number];
}

export interface MeasurementSnap {
  kind: 'vertex' | 'edge' | 'face' | 'ground';
  objectId?: string;
  primitiveId?: string;
  /** Incident edges for vertices; the single underlying edge for an edge snap. */
  edges?: MeasurementEdge[];
}

export interface MeasurementPoint {
  id: string;
  longitude: number;
  latitude: number;
  elevationMeters: number;
  elevationAvailable: boolean;
  surface: MeasurementSurface;
  buildingHeightMeters?: number;
  snap?: MeasurementSnap;
}

export interface MeasurementState {
  /** Omitted by older callers: distance, metric. */
  kind?: MeasurementKind;
  units?: 'metric' | 'imperial';
  status: MeasurementStatus;
  points: MeasurementPoint[];
  preview: MeasurementPoint | null;
  showComponents?: boolean;
}

export interface PlaceDetails {
  id: string;
  name: string;
  context: string;
  longitude: number;
  latitude: number;
  temperatureC: number;
  weatherLabel: string;
}

export type TimeRange =
  | '30m'
  | '1h'
  | '1d'
  | '1w'
  | '1mo'
  | '3mo'
  | '6mo'
  | '1y';

export const TIME_RANGE_OPTIONS: ReadonlyArray<{ value: TimeRange; label: string }> = [
  { value: '30m', label: '30 minutes' },
  { value: '1h', label: '1 hour' },
  { value: '1d', label: '1 day' },
  { value: '1w', label: '1 week' },
  { value: '1mo', label: '1 month' },
  { value: '3mo', label: '3 months' },
  { value: '6mo', label: '6 months' },
  { value: '1y', label: '1 year' },
];

export type UrbanLayerId =
  | 'poi'
  | 'buildings-3d'
  | 'synthetic-buildings'
  | 'population'
  | 'public-facilities'
  | 'traffic'
  | 'sumo-network'
  | 'flood'
  | 'flood-history'
  | 'flood-satellite'
  | 'rain'
  | 'planning'
  | 'land-price'
  | 'parcels'
  | 'road-density'
  | 'green-area';

export type UrbanLayerStatus = 'available' | 'not-connected' | 'loading' | 'error';

export interface UrbanLayerDefinition {
  id: UrbanLayerId;
  label: string;
  description: string;
  category: 'built-environment' | 'mobility' | 'environment' | 'planning';
  enabledByDefault: boolean;
  status: UrbanLayerStatus;
  supportsTimeRange: boolean;
  supportsOpacity: boolean;
}

export type LayerState = Partial<Record<UrbanLayerId, boolean>>;
export type LayerOpacityState = Partial<Record<UrbanLayerId, number>>;

export interface PointSelection {
  kind: 'point';
  longitude: number;
  latitude: number;
  zoom: number;
  features: Array<{ id: string; label: string; layer: string; isNamedPlace?: boolean }>;
}

export type MapSelection = PointSelection | null;
