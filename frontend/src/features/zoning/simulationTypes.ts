export const simulationDefaults = {
  residential_m2_per_person: 35, work_m2_per_staff: 20, visitors_per_100m2_day: 10,
  green_open_percent: 30, rainfall_mm: 60,
  landscape_mode: 'preserve' as 'preserve' | 'redesign', traffic_radius_m: 750,
};
export type SimulationSettings = typeof simulationDefaults;
export interface SimulationStudy {
  id: string; plan_id: string; revision: number; scenario_id: string; model_version: string;
  native_work_estimate: { sumo_runs: number; swmm_runs: number };
}
export interface SimulationJob {
  id: string; study_id: string; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'partial' | 'cancelled';
  result_id: string | null; cancel_requested: boolean; error: string | null;
  progress: { module?: string; done?: number; total?: number } | null;
}
export interface SimulationResult {
  id: string; mode: string; model_version: string;
  context?: { development_context?: {
    surfaces?: {status: string; note: string; landscape_mode: string; scope: string; unclassified_surface_m2: number; mapped_green_m2: number; landcover?: {dataset?: string; year?: number} | null};
    traffic?: {status: string; source: string; note: string; network: string; radius_m: number; background_vehicles_hour: number; snapshot_id: string | null; captured_at: string | null; network_source?: string | null};
    inventory?: {status: string; source: string}; capacity?: {status: string; source: string};
  } };
  options: { id: string; comparison: ComparisonRow[]; traffic_comparison?: ComparisonRow[]; drainage_comparison?: ComparisonRow[]; state: {
    metrics: Record<string, number | null>;
    vietnam_planning_requirements?: { source_url: string; density_checks: {project_id: string; status: string; maximum_percent: number | null}[] };
    traffic?: { runs: { hour_local: number; completed_vehicles: number; unfinished_vehicles: number;
      undeparted_vehicles: number; mean_completed_delay_seconds: number | null }[] };
  } }[];
}
export interface ComparisonRow {
  metric: string; before: number | null; after: number | null; delta: number | null;
  unit: string; comparability: string; comparability_reason?: string | null; hour_local?: number; seed?: number;
  trip_population_complete?: boolean;
  scenario_values?: {before: number | null; after: number | null; delta: number | null; basis: string};
}
