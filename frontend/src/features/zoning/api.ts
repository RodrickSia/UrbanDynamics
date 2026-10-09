import { API_BASE_URL } from '../../services/api';

export async function zoningRequest<T>(path = '', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1/zoning/plans${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Plan request failed (${response.status})`);
  return data as T;
}
