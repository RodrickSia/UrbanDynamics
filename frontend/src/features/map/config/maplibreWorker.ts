import mapLibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

type MapLibreWorkerApi = Pick<typeof import('maplibre-gl'), 'setWorkerUrl'>;

export function configureMapLibreWorker(maplibregl: MapLibreWorkerApi): void {
  maplibregl.setWorkerUrl(mapLibreWorkerUrl);
}
