import type { PolygonGeometry } from './types';

export const indicatorFields = [
  ['net_area_factor', 'Usable floor area factor', .8, .1, 1],
  ['residential_m2_per_person', 'Residential m² / person', 35, 5, 500],
  ['residential_m2_per_home', 'Residential m² / home', 70, 10, 1000],
  ['work_m2_per_job', 'Workplace m² / job', 20, 5, 500],
  ['labour_force_percent', 'Labour force (%)', 50, 0, 100],
  ['residential_kwh_person_day', 'Residential kWh / person / day', 3, 0, 100],
  ['workplace_kwh_m2_day', 'Workplace kWh / m² / day', .14, 0, 10],
  ['residential_l_person_day', 'Residential L / person / day', 120, 0, 1000],
  ['workplace_l_job_day', 'Workplace L / job / day', 45, 0, 1000],
  ['residential_waste_kg_person_day', 'Residential waste kg / person / day', 1, 0, 20],
  ['workplace_waste_kg_job_day', 'Workplace waste kg / job / day', .5, 0, 20],
  ['transit_radius_m', 'Transit radius (m)', 500, 100, 2000],
] as const;
export type IndicatorAssumptions = Record<typeof indicatorFields[number][0], number>;
export const indicatorDefaults = Object.fromEntries(indicatorFields.map(([key,,value]) => [key,value])) as IndicatorAssumptions;
export const indicatorMetrics = [
  ['population', 'Population', 'people'], ['energy_kwh_day', 'Energy use', 'kWh/day'],
  ['water_m3_day', 'Water use', 'm³/day'], ['waste_kg_day', 'Waste produced', 'kg/day'],
  ['housing_capacity', 'Housing capacity', 'homes'], ['jobs_needed', 'Jobs needed', 'jobs'],
  ['jobs_capacity', 'Jobs capacity', 'jobs'], ['jobs_balance', 'Jobs balance', 'jobs'],
] as const;
export type AreaMetrics = Record<typeof indicatorMetrics[number][0], number | null>;
export interface AreaShare { code: string | null; label: string; color: string; area_m2: number; percent: number }
export interface AreaIndicators {
  area_m2: number; geometry: PolygonGeometry; revision: number | null;
  baseline: AreaMetrics; proposal: (AreaMetrics & { buildings: number }) | null;
  existing_buildings?: { status: 'estimated' | 'partial' | 'unavailable'; count: number;
    floor_area_m2: number | null; source: string; coverage: string };
  land_use: AreaShare[] | null; zoning: AreaShare[];
  population_source: { status: string; year: number | null; coverage_percent: number; covered_population: number | null; source: string };
  transit: { status: string; coverage_percent: number | null; mapped_coverage_percent?: number; stop_count?: number;
    radius_m?: number; source?: string; captured_at?: string; method?: string };
  assumptions: IndicatorAssumptions; notes: string[]; issues: string[];
}
