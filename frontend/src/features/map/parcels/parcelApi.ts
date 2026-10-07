import { requestJson } from '../../../services/api';

export interface PriceCandidate {
  feature_id: string;
  distance_m: number;
  properties: Record<string, unknown>;
}
export interface ParcelDetail {
  parcel: { id: number; area_m2: number; source_fragments: number; conflicting_land_use: boolean } & Record<string, unknown>;
  land_use: { code: string | null; label: string | null; color: string; color_source: string };
  area_source: 'map_geometry';
  planning: Array<{ label: string; area_m2: number }>;
  price: {
    status: 'reference' | 'unavailable' | 'ambiguous' | 'unverified' | 'unsupported_land_use';
    method: string;
    source_land_use: string | null;
    normalized_land_use: string | null;
    price_category: 'Residential' | 'Commercial' | 'Other non-agricultural' | null;
    classification_confidence: 'high' | 'medium' | 'low' | 'unmapped';
    valuation_confidence: 'high' | 'medium' | 'low' | 'none';
    road_match_status: string;
    geometry_review_status: string;
    provenance: string;
    unit_price_vnd_m2: number | null;
    estimated_land_total_vnd: number | null;
    selected: PriceCandidate | null;
    candidates: PriceCandidate[];
  };
}

export async function getParcelDetail(id: string, signal: AbortSignal): Promise<ParcelDetail> {
  const result = await requestJson(`/api/v1/parcels/${encodeURIComponent(id)}`, signal);
  if (!result.parcel || !result.land_use || !result.price || !Array.isArray(result.planning))
    throw new Error('Invalid parcel detail');
  return result as unknown as ParcelDetail;
}

export function sourceLink(value: unknown): string | undefined {
  if (typeof value !== 'string') return;
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined; }
  catch { return; }
}
