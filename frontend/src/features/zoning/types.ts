import type { LineString, MultiPolygon, Polygon, Position } from 'geojson';

export type PolygonGeometry = Polygon | MultiPolygon;
export type SketchGeometry = PolygonGeometry | LineString;
export interface ZoneType {
  id: string; code: string; name: string; color: string; description: string; uses: string;
  max_height: number | null; max_floors: number | null; coverage: number | null; far: number | null;
  setback_front: number | null; setback_side: number | null; setback_rear: number | null;
  source: string; version: number; status: 'proposal';
}
export type TypeInput = Omit<ZoneType, 'id' | 'version' | 'status'>;
export const RULE_FIELDS = [
  ['max_height', 'Maximum height (m)', 1000], ['max_floors', 'Maximum floors', 200],
  ['coverage', 'Coverage (%)', 100], ['far', 'FAR', 100],
  ['setback_front', 'Front setback (m)', 1000], ['setback_side', 'Side setback (m)', 1000],
  ['setback_rear', 'Rear setback (m)', 1000],
] as const;
export interface Zone {
  id: string; type_id: string; geometry: PolygonGeometry; area_m2: number; revision: number; source: string;
  label_point: [number, number];
}
export interface Scenario {
  id: string; name: string; kind: 'reference' | 'proposal'; locked: boolean; zones: Zone[];
  can_undo: boolean; can_redo: boolean;
}
export interface Plan {
  id: string; name: string; description: string; horizon: number | null;
  study_area: PolygonGeometry; area_m2: number; revision: number; updated_at: string;
  status: 'draft'; baseline: { version: string; captured_at: string; status: string; source: string };
  types: ZoneType[]; scenarios: Scenario[];
}
export type PlanSummary = Pick<Plan, 'id' | 'name' | 'area_m2' | 'updated_at' | 'revision'>;
export interface Command {
  revision: number; action: string; scenario_id: string | null; payload: Record<string, unknown>;
}
export interface Preview {
  zones: Zone[]; overlap_m2: number; clipped_outside_m2: number; affected_ids: string[]; policy: string;
}
export interface Indicators {
  study_m2: number; assigned_m2: number; unassigned_m2: number; changed_m2: number;
  rows: { type_id: string; area_m2: number; comparison_m2: number; delta_m2: number;
    far_bound_m2: number | null; footprint_bound_m2: number | null }[];
  findings: { id: string; severity: string; certainty: string; zone_id: string | null; message: string; geometry?: PolygonGeometry }[];
  comparison_status: string; area_basis: string;
}
export type Tool = 'study' | 'edit-study' | 'draw' | 'reshape' | 'split' | null;
export interface Sketch { tool: Tool; points: Position[]; geometry: SketchGeometry | null }
export interface ZoningBridge {
  active: boolean; plan: Plan | null; scenario: Scenario | null; selected: string[];
  sketch: Sketch; preview: Preview | null; opacity: number; visible: boolean; showParcels: boolean;
  parcelAvailable: boolean; busy: boolean;
  onPick: (id: string | null, multiple: boolean) => void;
  onSketch: (sketch: Sketch) => void;
  onFinish: () => void; onCancel: () => void;
  focus: { key: number; geometry: PolygonGeometry } | null;
}
