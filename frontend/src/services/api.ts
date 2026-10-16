/** Public dataset API. Never use backend-internal hosts returned in TileJSON. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '';
export type VectorDataset =
  | 'flood_history'
  | 'flood_satellite'
  | 'flood_risk'
  | 'land_price'
  | 'parcels'
  | 'synthetic_buildings'
  | 'sumo_network'
  | 'traffic'
  | 'sumo_simulation';
export type Dataset = VectorDataset | 'population';
export type Palette = 'pseudocolor' | 'greyscale' | 'fire';
export type Bounds = [number, number, number, number];
export interface DateQuery {
  start?: string;
  end?: string;
}
export interface TrafficPeriod {
  weekday: number;
  period: string;
}
export interface SumoSimulationCatalog {
  available: boolean;
  network_input: boolean;
  network_edges: number;
  matched_observations: number;
}
export interface CachedSumoScenario {
  runId: string;
  weekday: number;
  period: string;
  generatedAt?: string;
  metadata?: Record<string, unknown>;
}
export interface CatalogLayer {
  id: string;
  available: boolean;
  stale?: boolean;
  updated_at?: string;
}
export interface FeatureSummary {
  type: 'FeatureCollection';
  features: Array<{ properties: Record<string, unknown> }>;
  metadata: Record<string, unknown>;
}
export async function getTrafficCatalog(signal?: AbortSignal) {
  const result = await requestJson('/api/v1/traffic/catalog', signal);
  requireShape(typeof result.available === 'boolean' && typeof result.network_available === 'boolean');
  return {
    available: result.available === true,
    networkAvailable: result.network_available === true,
  };
}
export async function getSumoSimulationCatalog(signal?: AbortSignal): Promise<SumoSimulationCatalog> {
  const result = await requestJson('/api/v1/traffic/sumo-simulations/catalog', signal);
  requireShape(typeof result.available === 'boolean');
  return {
    available: result.available === true,
    network_input: result.network_input === true,
    network_edges: Number(result.network_edges ?? 0),
    matched_observations: Number(result.matched_observations ?? 0),
  };
}
export async function getLatestSumoScenario(signal?: AbortSignal): Promise<CachedSumoScenario | null> {
  try {
    const cached = await requestJson('/api/v1/traffic/sumo-simulations/latest', signal);
    requireShape(
      typeof cached.run_id === 'string' &&
        typeof cached.weekday === 'number' &&
        typeof cached.period === 'string',
    );
    return {
      runId: cached.run_id as string,
      weekday: cached.weekday as number,
      period: cached.period as string,
      generatedAt: typeof cached.generated_at === 'string' ? cached.generated_at : undefined,
      metadata: cached.metadata && typeof cached.metadata === 'object' ? object(cached.metadata) : undefined,
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
export async function getSumoSimulationRun(runId: string, signal?: AbortSignal) {
  const result = await requestJson(`/api/v1/traffic/sumo-simulations/runs/${runId}`, signal);
  requireShape(typeof result.status === 'string');
  return {
    status: result.status as 'queued' | 'running' | 'completed' | 'failed',
    error: typeof result.error === 'string' ? result.error : undefined,
    metadata: result.metadata && typeof result.metadata === 'object' ? object(result.metadata) : undefined,
  };
}
export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 503 ? 'Dataset temporarily unavailable' : `Data request failed (${status})`);
  }
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Invalid API response');
  return value as Record<string, unknown>;
}
function requireShape(valid: boolean): void {
  if (!valid) throw new Error('Invalid API response');
}
export async function requestJson(
  path: string,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
      : AbortSignal.timeout(15000),
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new ApiError(response.status);
  return object(await response.json());
}
export async function getLayerCatalog(signal?: AbortSignal): Promise<CatalogLayer[]> {
  const result = await requestJson('/api/v1/layers', signal);
  requireShape(Array.isArray(result.layers));
  return (result.layers as unknown[]).map((value) => {
    const row = object(value);
    requireShape(typeof row.id === 'string' && typeof row.available === 'boolean');
    return {
      id: row.id as string,
      available: row.available as boolean,
      stale: row.stale === true,
      updated_at: typeof row.updated_at === 'string' ? row.updated_at : undefined,
    };
  });
}
export async function getPopulationCatalog(signal?: AbortSignal) {
  const result = await requestJson('/api/v1/population', signal);
  requireShape(typeof result.available === 'boolean' && Array.isArray(result.years));
  const years = (result.years as unknown[]).map((value) => {
    const year = object(value).year;
    requireShape(
      typeof year === 'number' && Number.isInteger(year) && year >= 1900 && year <= 2200,
    );
    return year as number;
  });
  return {
    available: result.available === true && years.length > 0,
    years: [...new Set(years)].sort((a, b) => a - b),
  };
}
export function dateQuery(start: string, end: string): DateQuery {
  for (const value of [start, end])
    if (value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value))))
      throw new Error('Use a valid date');
  if (start && end && start >= end) throw new Error('Start must be before end');
  return {
    ...(start ? { start: `${start}T00:00:00Z` } : {}),
    ...(end ? { end: `${end}T00:00:00Z` } : {}),
  };
}
export function queryString(values: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value !== undefined) params.set(key, value);
  return params.size ? `?${params}` : '';
}
export function tileUrl(
  dataset: Dataset,
  dates: DateQuery = {},
  year = 2024,
  palette: Palette = 'pseudocolor',
  trafficPeriod?: TrafficPeriod,
  sumoRunId?: string,
) {
  const path =
    dataset === 'population'
      ? `/api/v1/population/${year}/tiles/{z}/{x}/{y}.png${queryString({ palette, render: '2' })}`
      : dataset === 'traffic'
        ? `/api/v1/traffic/prediction/tiles/{z}/{x}/{y}.pbf${queryString(trafficPeriod ? { weekday: String(trafficPeriod.weekday), period: trafficPeriod.period } : {})}`
      : dataset === 'sumo_network'
        ? `/api/v1/traffic/network/tiles/{z}/{x}/{y}.pbf`
      : dataset === 'sumo_simulation'
        ? `/api/v1/traffic/sumo-simulations/runs/${sumoRunId ?? ''}/features`
      : `/api/v1/layers/${dataset}/tiles/{z}/{x}/{y}.pbf${queryString(
          dataset === 'land_price' || dataset === 'parcels'
            ? (dataset === 'parcels' ? { schema: '2' } : {})
            : { ...dates, ...(dataset === 'flood_history' ? { schema: '2' } : {}) },
        )}`;
  return `${API_BASE_URL}${path}`;
}
export async function getFeatures(
  dataset: VectorDataset,
  bounds?: Bounds,
  dates: DateQuery = {},
  signal?: AbortSignal,
  trafficPeriod?: TrafficPeriod,
  sumoRunId?: string,
): Promise<FeatureSummary> {
  const result = await requestJson(
    dataset === 'sumo_simulation'
      ? `/api/v1/traffic/sumo-simulations/runs/${sumoRunId ?? ''}/features`
      : dataset === 'sumo_network'
      ? `/api/v1/traffic/network${queryString({ bbox: bounds?.join(','), limit: '1' })}`
      : dataset === 'traffic'
      ? `/api/v1/traffic/prediction${queryString({ ...(trafficPeriod ? { weekday: String(trafficPeriod.weekday), period: trafficPeriod.period } : {}), bbox: bounds?.join(','), limit: '1' })}`
      : `/api/v1/layers/${dataset}/features${queryString({
      ...(dataset === 'land_price' || dataset === 'parcels' ? {} : dates),
      bbox: bounds?.join(','),
      limit: '1',
      })}`,
    signal,
  );
  requireShape(result.type === 'FeatureCollection' && Array.isArray(result.features));
  return {
    type: 'FeatureCollection',
    features: (result.features as unknown[]).map((value) => ({
      properties: object(object(value).properties),
    })),
    metadata: object(result.metadata),
  };
}
export async function getPopulationStats(year: number, bounds: Bounds, signal?: AbortSignal) {
  const result = await requestJson(
    `/api/v1/population/${year}/stats${queryString({ bbox: bounds.join(',') })}`,
    signal,
  );
  const stats = object(result.statistics);
  requireShape(typeof stats.pixel_count === 'number' && Number.isFinite(stats.pixel_count));
  return stats.pixel_count as number;
}
export async function getPopulationValue(
  year: number,
  lng: number,
  lat: number,
  signal?: AbortSignal,
) {
  const result = await requestJson(
    `/api/v1/population/${year}/value${queryString({ lng: String(lng), lat: String(lat) })}`,
    signal,
  );
  requireShape(
    result.population === null ||
      (typeof result.population === 'number' && Number.isFinite(result.population)),
  );
  return result.population as number | null;
}
