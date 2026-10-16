import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getLayerCatalog,
  getPopulationCatalog,
  getFeatures,
  getTrafficCatalog,
  getSumoSimulationCatalog,
  getLatestSumoScenario,
  tileUrl,
  type Palette,
  type DateQuery,
  type CatalogLayer,
  type TrafficPeriod,
} from '../../../services/api';
import { URBAN_LAYERS } from '../layers/layerRegistry';
import type { LayerState, MapMode } from '../types/map';
import {
  DATASETS,
  isDataLayer,
  type DataLayerId,
  type DataSelection,
  type LayerReport,
} from './datasets';

interface CatalogState {
  status: 'loading' | 'ready' | 'error';
  available: boolean;
  stale?: boolean;
}
export function useBackendLayers(layers: LayerState, mode: MapMode = '3d') {
  const [catalog, setCatalog] = useState<Partial<Record<DataLayerId, CatalogState>>>({});
  const [years, setYears] = useState<number[]>([]);
  const [chosenYear, setYear] = useState<number | null>(null);
  const [palette, setPalette] = useState<Palette>('pseudocolor');
  const [dates, setDates] = useState<DateQuery>({});
  const [trafficSchedule, setTrafficSchedule] = useState<TrafficPeriod>(() => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
    const minute = Number(value.minute) < 30 ? '00' : '30';
    const weekday = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', weekday: 'long' }).format(new Date());
    const weekdayNumber = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].indexOf(weekday) + 1;
    return { weekday: weekdayNumber, period: `${value.hour}:${minute}` };
  });
  const [sumoRunId, setSumoRunId] = useState<string | null>(null);
  const [sumoRunStatus, setSumoRunStatus] = useState<'loading' | 'completed' | 'empty' | 'error' | null>(null);
  const [sumoRunError, setSumoRunError] = useState<string | null>(null);
  const [sumoRunMetadata, setSumoRunMetadata] = useState<Record<string, unknown> | null>(null);
  const [revision, setRevision] = useState(0);
  const [reports, setReports] = useState<Partial<Record<DataLayerId, LayerReport>>>({});
  const year =
    chosenYear !== null && years.includes(chosenYear)
      ? chosenYear
      : (years.filter((y) => y <= new Date().getFullYear()).at(-1) ?? years.at(-1) ?? 0);
  useEffect(() => {
    const controller = new AbortController();
    const save = (values: Partial<Record<DataLayerId, CatalogState>>) => {
      if (!controller.signal.aborted) setCatalog((current) => ({ ...current, ...values }));
    };
    void getPopulationCatalog(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setYears(result.years);
        save({ population: { status: 'ready', available: result.available } });
      })
      .catch(() => save({ population: { status: 'error', available: false } }));
    void getLayerCatalog(controller.signal)
      .then(async (result) => {
        const values: Partial<Record<DataLayerId, CatalogState>> = {};
        const ids = ['flood', 'flood-history', 'flood-satellite', 'land-price', 'parcels', 'synthetic-buildings'] as const;
        for (const id of ids) {
          const entry: CatalogLayer | undefined = result.find((row) => row.id === DATASETS[id]);
          values[id] = {
            status: 'ready',
            available: entry?.available ?? false,
            stale: entry?.stale,
          };
        }
        // Accept reviewed segments, spatial matches and published automatic road proxies.
        save({
          ...values,
          'land-price': {
            status: values['land-price']?.available ? 'loading' : 'ready',
            available: false,
          },
        });
        if (values['land-price']?.available) {
          try {
            const sample = await getFeatures('land_price', undefined, {}, controller.signal);
            save({
              'land-price': {
                status: 'ready',
                available: sample.features.some(
                  (f) =>
                    f.properties.geometry_reviewed === true ||
                    f.properties.match_confidence === 'spatially_checked' ||
                    (f.properties.publication_match_mode === 'automatic' &&
                      f.properties.match_confidence === 'automatic_reference' &&
                      Number(f.properties.residential_vnd_m2) > 0) ||
                    (f.properties.publication_match_mode === 'automatic' &&
                      f.properties.geometry_coverage === 'whole_named_road_proxy'),
                ),
              },
            });
          } catch {
            save({ 'land-price': { status: 'error', available: false } });
          }
        }
      })
      .catch(() =>
        save(
          Object.fromEntries(
            ['flood', 'flood-history', 'flood-satellite', 'land-price', 'parcels', 'synthetic-buildings'].map((id) => [
              id,
              { status: 'error', available: false },
            ]),
          ),
        ),
      );
    void getTrafficCatalog(controller.signal)
      .then((traffic) => save({
        traffic: { status: 'ready', available: traffic.available },
        'sumo-network': { status: 'ready', available: traffic.networkAvailable },
      }))
      .catch(() => save({
        traffic: { status: 'error', available: false },
        'sumo-network': { status: 'error', available: false },
      }));
    void getSumoSimulationCatalog(controller.signal)
      .then((result) => save({
        'sumo-simulation': { status: 'ready', available: result.available },
      }))
      .catch(() => save({ 'sumo-simulation': { status: 'error', available: false } }));
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!layers['sumo-simulation']) {
      setSumoRunId(null);
      setSumoRunStatus(null);
      setSumoRunError(null);
      setSumoRunMetadata(null);
      return;
    }
    const controller = new AbortController();
    setSumoRunId(null);
    setSumoRunStatus('loading');
    setSumoRunError(null);
    setSumoRunMetadata(null);
    void getLatestSumoScenario(controller.signal)
      .then((scenario) => {
        if (controller.signal.aborted) return;
        if (!scenario) {
          setSumoRunStatus('empty');
          return;
        }
        setSumoRunId(scenario.runId);
        setSumoRunStatus('completed');
        setSumoRunMetadata({
          ...scenario.metadata,
          weekday: scenario.weekday,
          period: scenario.period,
          generated_at: scenario.generatedAt,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSumoRunError(error instanceof Error ? error.message : 'Cached SUMO layer unavailable');
        setSumoRunStatus('error');
      });
    return () => {
      controller.abort();
    };
  }, [layers['sumo-simulation'], revision]);
  const definitions = useMemo(
    () =>
      URBAN_LAYERS.map((layer) =>
        isDataLayer(layer.id)
          ? {
              ...layer,
              status: catalog[layer.id]?.available
                ? ('available' as const)
                : catalog[layer.id]?.status === 'error'
                  ? ('error' as const)
                  : !catalog[layer.id] || catalog[layer.id]?.status === 'loading'
                    ? ('loading' as const)
                    : ('not-connected' as const),
            }
          : layer,
      ),
    [catalog],
  );
  const selections = useMemo<DataSelection[]>(
    () =>
      definitions.flatMap((layer) => {
        if (!isDataLayer(layer.id) || !layers[layer.id] || layer.status !== 'available') return [];
        const dataset = DATASETS[layer.id];
        if (dataset === 'sumo_simulation' && (!sumoRunId || sumoRunStatus !== 'completed')) return [];
        const sumoVolumeMax = Number(sumoRunMetadata?.max_estimated_cars_6h ?? 0);
        return [
          { id: layer.id, dataset, url: tileUrl(dataset, dates, year, palette,
            dataset === 'traffic' ? trafficSchedule : undefined, dataset === 'sumo_simulation' ? sumoRunId ?? undefined : undefined), year, dates,
            visible: layer.id !== 'synthetic-buildings' || mode === '3d',
            ...(dataset === 'traffic' ? { trafficPeriod: trafficSchedule } : {}),
            ...(dataset === 'sumo_simulation'
              ? { sumoRunId: sumoRunId ?? undefined, sumoVolumeMax }
              : {}),
          },
        ];
      }),
    [definitions, layers, year, palette, dates, trafficSchedule, sumoRunId, sumoRunStatus, sumoRunMetadata, mode],
  );
  const report = useCallback(
    (id: DataLayerId, value: LayerReport) =>
      setReports((current) =>
        current[id]?.status === value.status && current[id]?.message === value.message
          ? current
          : { ...current, [id]: value },
      ),
    [],
  );
  const retry = useCallback(() => {
    setRevision((n) => n + 1);
  }, []);
  return {
    catalog,
    definitions,
    selections,
    years,
    year,
    setYear,
    palette,
    setPalette,
    dates,
    setDates,
    trafficSchedule,
    setTrafficSchedule,
    sumoRunId,
    sumoRunStatus,
    sumoRunError,
    sumoRunMetadata,
    reports,
    report,
    retry,
    revision,
  };
}
export type BackendLayers = ReturnType<typeof useBackendLayers>;
