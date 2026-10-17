export interface CostArea { name: string; area_m2: number; factor: number; source: string }
export interface CostProfile {
  package: 'shell' | 'standard' | 'mid' | 'premium' | 'custom'; unit_price: number | null;
  rate_source: string; location_factor: number; access_factor: number; complexity_factor: number;
  foundation_factor: number; roof_factor: number; area_source: string; floor_area_m2: number | null;
  additional_areas: CostArea[]; additional_areas_confirmed: boolean;
}
export type ExtraName = 'piling' | 'design' | 'permit' | 'special';
export interface CostSettings {
  version: 1; profile: CostProfile; building_overrides: Record<string, CostProfile>;
  demolition_rate: number | null; demolition_area_m2: number | null; demolition_included: boolean;
  demolition_source: string; extras: Partial<Record<ExtraName, { amount: number; included: boolean }>>;
  vat_included: boolean; vat_pct: number; reserve_pct: number;
}
export interface ConstructionCostReport {
  plan_id: string; scenario_id: string; revision: number; currency: 'VND'; settings: CostSettings;
  status: 'estimate' | 'incomplete'; construction: number; demolition: number | null; extras: number;
  subtotal: number; vat: number; reserve: number; known_total: number; total: number | null;
  demolition_basis: string; warnings: string[];
  buildings: { id: string; name: string; parcel_id: string; physical_floor_m2: number; converted_m2: number;
    unit_price: number | null; adjustment: number; base: number | null; total: number | null;
    source: string; area_source: string; components: {name: string; area_m2: number; factor: number}[] }[];
  demolitions: { id: string; name: string; area_m2: number | null; cost: number | null; total: number | null; source: string }[];
}
export const costPackages = [
  ['shell', 'Shell + finishing labor', 3600000], ['standard', 'Standard turnkey', 5300000],
  ['mid', 'Mid-range turnkey', 6000000], ['premium', 'Premium · quote required', null],
  ['custom', 'Custom quote', null],
] as const;
export const costMoney = (value: number | null) => value === null ? 'Unknown' : `${value.toLocaleString('vi-VN', {maximumFractionDigits: 0})} ₫`;
export const costArea = (value: number | null) => value === null ? 'Unknown' : `${value.toLocaleString('vi-VN', {maximumFractionDigits: 2})} m²`;
