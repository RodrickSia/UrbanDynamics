import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { zoningRequest } from './api';

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(AbortSignal, 'timeout').mockImplementation((milliseconds) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), milliseconds);
    return controller.signal;
  });
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function delayedResponse(milliseconds: number) {
  const fetch = vi.fn((_url: string, options?: RequestInit) => new Promise<Response>((resolve, reject) => {
    const signal = options?.signal;
    const timer = setTimeout(() => resolve(new Response(JSON.stringify({ id: 'queued-job' }))), milliseconds);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

it.each(['runs', 'studies'])('accepts simulation %s preparation taking longer than twenty seconds', async (endpoint) => {
  const fetch = delayedResponse(30_000);
  const request = zoningRequest(`/plan/simulation/${endpoint}`, {});
  await vi.advanceTimersByTimeAsync(30_000);
  await expect(request).resolves.toEqual({ id: 'queued-job' });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('stops waiting after two minutes when simulation preparation does not respond', async () => {
  delayedResponse(180_000);
  const request = zoningRequest('/plan/simulation/runs', {});
  const rejected = expect(request).rejects.toMatchObject({ name: 'TimeoutError' });
  await vi.advanceTimersByTimeAsync(120_000);
  await rejected;
});

it('honors explicit cancellation before the simulation preparation deadline', async () => {
  delayedResponse(30_000);
  const controller = new AbortController();
  const request = zoningRequest('/plan/simulation/runs', {}, controller.signal);
  const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
  controller.abort();
  await rejected;
});
