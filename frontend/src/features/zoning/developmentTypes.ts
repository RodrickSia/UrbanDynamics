import type { PolygonGeometry } from './types';

export interface DevelopmentParcel {
  id: string; geometry: PolygonGeometry; area_m2: number; land_use: string | null;
  source: string; status: string; captured_at: string;
}
export interface BuildingFloor {
  floor: number; floor_height: number; space_use_id: string; counts_gfa: boolean; counts_far: boolean;
}
export interface FloorBand extends BuildingFloor { base_m: number; top_m: number; color: string }
export interface BuildingInput {
  id?: string | null; origin_id?: string | null; parcel_id: string; geometry: PolygonGeometry;
  name: string; floors: number; floor_height: number; space_use_id: string;
  counts_gfa: boolean; counts_far: boolean; template_id?: string | null; demolish?: boolean;
  floor_overrides?: BuildingFloor[];
}
export interface ProposedBuilding extends BuildingInput {
  id: string; height_m: number; footprint_m2: number; color: string;
  floor_stack?: FloorBand[];
  ground_anchor: { datum: string; offset_m: number; status: string };
}
export interface DevelopmentMetrics {
  footprint_m2: number; gfa_m2: number; far: number; coverage_pct: number;
  space_use_m2: Record<string, number>; buildings?: number; demolition_m2?: number;
  baseline_gfa_m2?: number | null; basis?: string;
}
export interface DevelopmentCheck {
  rule: string; actual: number | null; allowed: number | null; status: string; unit: string;
  source: string; assumed_limit: number | null; assumption_status: string;
}
export interface DevelopmentReport {
  metrics: DevelopmentMetrics; checks: DevelopmentCheck[]; rule_status: string;
}
export interface ParcelDevelopment extends DevelopmentReport {
  parcel: DevelopmentParcel;
  catalog: { version: number; space_uses: { id: string; name: string; color: string; default_floor_height: number }[];
    building_types: { id: string; version: number; name: string; floors: number; floor_height: number; space_use_id: string }[] };
}
export interface DevelopmentPreview extends DevelopmentReport { building: ProposedBuilding; parcel: DevelopmentParcel }
export interface DevelopmentBridge {
  active: boolean; parcel: DevelopmentParcel | null; selectedBuilding: string | null;
  preview: ProposedBuilding | null; onPickParcel: (id: string) => void;
  onPickBuilding: (id: string) => void;
  onDelete: () => void; onUndo: (redo: boolean) => void;
}

export function buildingInput(building: BuildingInput): BuildingInput {
  const { id, origin_id, parcel_id, geometry, name, floors, floor_height, space_use_id, counts_gfa, counts_far, template_id, demolish, floor_overrides } = building;
  return { id, origin_id, parcel_id, geometry, name, floors, floor_height, space_use_id, counts_gfa, counts_far, template_id, demolish, floor_overrides };
}
