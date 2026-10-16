import { API_BASE_URL } from '../../services/api';

export class ZoningRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export async function zoningRequest<T>(path = '', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1/zoning/plans${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail
      : Array.isArray(data.detail) ? data.detail.slice(0, 3).map((issue: {loc?: (string | number)[]; msg?: string}) =>
        `${issue.loc?.slice(1).join('.') || 'Input'}: ${issue.msg || 'Invalid value'}`).join('; ')
        : `Plan request failed (${response.status})`;
    throw new ZoningRequestError(detail, response.status);
  }
  return data as T;
}

export async function deleteZoningPlan(id: string, revision: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/zoning/plans/${encodeURIComponent(id)}?revision=${revision}`, {
    method: 'DELETE', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : `Unable to delete plan (${response.status})`);
  }
}
