import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getLayerCatalog,
  getPopulationCatalog,
  getFeatures,
  tileUrl,
  type Palette,
  type DateQuery,
  type CatalogLayer,
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
    return () => controller.abort();
  }, [revision]);
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
        return [
          { id: layer.id, dataset, url: tileUrl(dataset, dates, year, palette), year, dates,
            visible: layer.id !== 'synthetic-buildings' || mode === '3d' },
        ];
      }),
    [definitions, layers, year, palette, dates, mode],
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
    reports,
    report,
    retry,
    revision,
  };
}
export type BackendLayers = ReturnType<typeof useBackendLayers>;
