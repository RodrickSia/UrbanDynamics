export const simulationDefaults = {
  residential_m2_per_person: 35, work_m2_per_staff: 20, visitors_per_100m2_day: 10,
  green_open_percent: 30, rainfall_mm: 60,
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
  options: { id: string; comparison: {metric: string; before: number | null; after: number | null; delta: number | null; unit: string; comparability: string}[]; state: {
    metrics: Record<string, number | null>;
    vietnam_planning_requirements?: { source_url: string; density_checks: {project_id: string; status: string; maximum_percent: number | null}[] };
    traffic?: { runs: { hour_local: number; completed_vehicles: number; unfinished_vehicles: number;
      undeparted_vehicles: number; mean_completed_delay_seconds: number | null }[] };
  } }[];
}
