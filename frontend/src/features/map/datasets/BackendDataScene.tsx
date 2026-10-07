import type { Map as MapLibreMap, ErrorEvent as MapErrorEvent, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import {
  ApiError,
  getFeatures,
  getPopulationStats,
  getPopulationValue,
  type Bounds,
} from '../../../services/api';
import type { LayerOpacityState } from '../types/map';
import { type DataSelection, type DataLayerId, type LayerReport } from './datasets';
import { dataSourceId, datasetStyle } from './datasetStyle';
import { floodLocationDetails } from './floodLocation';
import { populationRasterSource, viewportProbeDelayAfterMove } from './populationRaster';
import './data.css';

export interface BackendBridge {
  selections: DataSelection[];
  opacity: LayerOpacityState;
  revision: number;
  report: (id: DataLayerId, report: LayerReport) => void;
}
function viewportBounds(map: MapLibreMap): Bounds | null {
  const bounds = map.getBounds();
  const result: Bounds = [
    Math.max(-180, bounds.getWest()),
    Math.max(-90, bounds.getSouth()),
    Math.min(180, bounds.getEast()),
    Math.min(90, bounds.getNorth()),
  ];
  return result.every(Number.isFinite) && result[0] < result[2] && result[1] < result[3]
    ? result
    : null;
}
function DatasetSource({
  map,
  selection,
  opacity,
  revision,
  report,
}: {
  map: MapLibreMap;
  selection: DataSelection;
  opacity: number;
  revision: number;
  report: BackendBridge['report'];
}) {
  const current = useRef(selection);
  const sourceId = dataSourceId(selection.id);
  const opacityRef = useRef(opacity);
  useEffect(() => {
    current.current = selection;
    opacityRef.current = opacity;
  }, [selection, opacity]);
  useEffect(() => {
    const selectedAtAttach = current.current;
    let disposed = false,
      styleReady = false,
      timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined;
    let tileError = false;
    const publish = (status: LayerReport['status'], message: string) => {
      if (!disposed) report(selectedAtAttach.id, { status, message });
    };
    const probe = async () => {
      request?.abort();
      request = new AbortController();
      const signal = request.signal;
      const bounds = viewportBounds(map);
      if (!bounds) {
        publish('ready', 'Move to Vietnam to inspect coverage');
        return;
      }
      const selected = current.current;
      if (selected.dataset === 'parcels') {
        publish(
          tileError ? 'error' : 'ready',
          tileError
            ? 'Parcel tiles unavailable · retry'
            : map.getZoom() < 16
              ? 'Zoom in to level 16 to view parcel boundaries'
              : 'Click a parcel to inspect its attributes',
        );
        return;
      }
      if (
        selected.dataset === 'population' &&
        (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) > 4
      ) {
        publish(
          tileError ? 'error' : 'ready',
          tileError ? 'Tiles unavailable · retry' : 'Zoom in to inspect coverage',
        );
        return;
      }
      publish('loading', 'Checking this area…');
      try {
        const count =
          selected.dataset === 'population'
            ? await getPopulationStats(selected.year, bounds, signal)
            : (await getFeatures(selected.dataset, bounds, selected.dates, signal)).features.length;
        if (signal.aborted) return;
        publish(
          count === 0 ? 'empty' : tileError ? 'error' : 'ready',
          count === 0
            ? 'No data in this area'
            : tileError
              ? 'Tiles unavailable · retry'
              : 'Data available in this area',
        );
      } catch (error) {
        if (signal.aborted) return;
        if (selected.dataset === 'population' && error instanceof ApiError && error.status === 404)
          publish('empty', 'No data in this area');
        else publish('error', 'Data unavailable · retry');
      }
    };
    const schedule = (delay = 300) => {
      clearTimeout(timer);
      request?.abort();
      timer = setTimeout(() => void probe(), delay);
    };
    const attach = () => {
      styleReady = true;
      tileError = false;
      if (!map.getSource(sourceId)) {
        const raster = selectedAtAttach.dataset === 'population';
        map.addSource(
          sourceId,
          raster
            ? populationRasterSource(selectedAtAttach.url)
            : {
                type: 'vector',
                tiles: [selectedAtAttach.url],
                minzoom: selectedAtAttach.dataset === 'parcels' ? 16 : 0,
                maxzoom: 18,
                attribution: 'UrbanDynamics · published datasets',
              },
        );
      }
      if (!map.getLayer(sourceId)) {
        // Preserve readable overlay order even if population is enabled last.
        const order = [
          'population',
          'parcels',
          'flood',
          'flood-satellite',
          'land-price',
          'flood-history',
        ].map((id) => `dataset-${id}`);
        const before = map
          .getStyle()
          .layers.find(
            (layer) =>
              order.indexOf(layer.id) > order.indexOf(sourceId) ||
              layer.type === 'symbol' ||
              layer.type === 'fill-extrusion' ||
              String(layer.type) === 'custom',
          )?.id;
        map.addLayer(datasetStyle(selectedAtAttach), before);
      }
      applyOpacity(map, selectedAtAttach, opacityRef.current);
      publish('loading', 'Loading…');
      schedule();
    };
    const onError = (event: MapErrorEvent) => {
      if (!('sourceId' in event) || event.sourceId !== sourceId) return;
      // Empty tiles (204) are valid; viewport inspection determines no-data state.
      if ('status' in event.error && event.error.status === 204) return;
      tileError = true;
      publish('error', 'Tiles unavailable · retry');
    };
    const styleLoading = () => {
      styleReady = false;
      request?.abort();
      clearTimeout(timer);
    };
    const moved = () => {
      if (styleReady)
        schedule(viewportProbeDelayAfterMove(current.current.dataset));
    };
    const moving = () => {
      request?.abort();
      clearTimeout(timer);
    };
    const settled = () => {
      if (!map.getSource(sourceId) && map.isStyleLoaded()) attach();
    };
    map.on('style.load', attach);
    map.on('styledataloading', styleLoading);
    map.on('moveend', moved);
    map.on('movestart', moving);
    map.on('error', onError);
    map.on('idle', settled);
    if (map.isStyleLoaded()) attach();
    return () => {
      disposed = true;
      request?.abort();
      clearTimeout(timer);
      map.off('style.load', attach);
      map.off('styledataloading', styleLoading);
      map.off('moveend', moved);
      map.off('movestart', moving);
      map.off('error', onError);
      map.off('idle', settled);
      if (map.getLayer(sourceId)) map.removeLayer(sourceId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [map, sourceId, selection.id, selection.dataset, selection.url, revision, report]);
  useEffect(() => {
    applyOpacity(map, selection, opacity);
  }, [map, selection, opacity]);
  return null;
}
function applyOpacity(map: MapLibreMap, selection: DataSelection, opacity: number) {
  const id = dataSourceId(selection.id);
  if (!map.getLayer(id)) return;
  const type =
    selection.dataset === 'population'
      ? 'raster'
      : selection.dataset === 'flood_history'
        ? 'circle'
        : selection.dataset === 'land_price'
          ? 'line'
          : 'fill';
  const multiplier = selection.dataset === 'parcels' ? 0.35 : type === 'fill' ? 0.6 : 1;
  map.setPaintProperty(id, `${type}-opacity`, opacity * multiplier);
}
const FIELDS: Record<string, string> = {
  location: 'Reported location',
  current_admin_unit: 'Current ward (source)',
  location_accuracy: 'Location accuracy',
  observed_at: 'Observed',
  depth_min_cm: 'Min depth (cm)',
  depth_max_cm: 'Max depth (cm)',
  cause: 'Cause',
  spatial_precision: 'Spatial precision',
  mask_mode: 'Classification',
  status: 'Indicator',
  rain_3h_mm: 'Rain / 3 h (mm)',
  threshold_p90_3h_mm: 'Threshold (mm)',
  issued_at: 'Issued',
  road: 'Road',
  start: 'From',
  end: 'To',
  residential_vnd_m2: 'Residential (VND/m²)',
  commercial_vnd_m2: 'Commercial (VND/m²)',
  effective_from: 'Effective from',
  price_kind: 'Price type',
  other_nonagricultural_vnd_m2: 'Other non-agricultural (VND/m²)',
  publication_match_mode: 'Match mode',
  geometry_coverage: 'Geometry coverage',
  review_note: 'Coverage note',
  source_url: 'Official source',
  pdf_page: 'Annex page',
  uniq_id: 'Parcel ID',
  tinh: 'Province / city',
  quan: 'District',
  phuong: 'Ward',
  to_ban_do: 'Map sheet',
  thua: 'Plot number',
  mdsdd: 'Land-use code',
  loai_dat_qh: 'Planned land use',
  quyet_dinh: 'Decision',
  do_an: 'Plan',
  population: 'People / source cell',
};
export function BackendDataScene({
  map,
  bridge,
  interactive,
}: {
  map: MapLibreMap | null;
  bridge: BackendBridge;
  interactive: boolean;
}) {
  return (
    <>
      {map &&
        bridge.selections.map((selection) => (
          <DatasetSource
            key={selection.id}
            map={map}
            selection={selection}
            opacity={bridge.opacity[selection.id] ?? 0.8}
            revision={bridge.revision}
            report={bridge.report}
          />
        ))}
      {interactive && (
        <DatasetInspection
          key={bridge.selections.map((s) => s.url).join('|')}
          map={map}
          bridge={bridge}
        />
      )}
    </>
  );
}
function DatasetInspection({ map, bridge }: { map: MapLibreMap | null; bridge: BackendBridge }) {
  const [inspection, setInspection] = useState<Record<string, unknown> | null>(null);
  const current = useRef(bridge);
  useEffect(() => {
    current.current = bridge;
  }, [bridge]);
  const selectionKey = bridge.selections.map((s) => s.url).join('|');
  useEffect(() => {
    if (!map) return;
    let request: AbortController | undefined;
    const click = (event: MapMouseEvent) => {
      request?.abort();
      const selections = current.current.selections;
      const ids = selections
        .filter((s) => s.dataset !== 'population')
        .map((s) => dataSourceId(s.id))
        .filter((id) => map.getLayer(id));
      const hit = ids.length
        ? map.queryRenderedFeatures(event.point, { layers: ids })[0]
        : undefined;
      if (hit) {
        setInspection(
          hit.layer.id === dataSourceId('flood-history')
            ? floodLocationDetails(hit.properties)
            : hit.properties,
        );
        return;
      }
      const population = selections.find((s) => s.dataset === 'population');
      if (!population) {
        setInspection(null);
        return;
      }
      request = new AbortController();
      const signal = request.signal;
      setInspection({ population: 'Loading…' });
      void getPopulationValue(population.year, event.lngLat.lng, event.lngLat.lat, signal)
        .then((value) => {
          if (!signal.aborted) setInspection({ population: value === null ? 'No data' : value });
        })
        .catch(() => {
          if (!signal.aborted) setInspection({ population: 'Sample unavailable' });
        });
    };
    map.on('click', click);
    return () => {
      request?.abort();
      map.off('click', click);
    };
  }, [map, selectionKey]);
  return (
    <>
      {inspection && bridge.selections.length > 0 && (
        <aside className="dataset-inspection glass-panel" aria-label="Dataset details">
          <button
            type="button"
            className="quiet-icon-button"
            aria-label="Close dataset details"
            onClick={() => setInspection(null)}
          >
            ×
          </button>
          <dl>
            {Object.entries(FIELDS)
              .filter(([key]) => inspection[key] !== undefined && inspection[key] !== null)
              .map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {typeof inspection[key] === 'number'
                      ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(
                          inspection[key] as number,
                        )
                      : String(inspection[key]).replaceAll('_', ' ')}
                  </dd>
                </div>
              ))}
          </dl>
        </aside>
      )}
    </>
  );
}
