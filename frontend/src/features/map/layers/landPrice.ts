import type { Map as MapLibreMap, MapMouseEvent, Popup } from 'maplibre-gl';

import { API_BASE_URL } from '../../../services/api';

export const LAND_PRICE_SOURCE_ID = 'urban-land-price';
export const LAND_PRICE_CASE_ID = 'urban-land-price-casing';
export const LAND_PRICE_LINE_ID = 'urban-land-price-line';

export function setLandPriceLayer(map: MapLibreMap, enabled: boolean, opacity: number) {
  if (!map.getSource(LAND_PRICE_SOURCE_ID)) {
    map.addSource(LAND_PRICE_SOURCE_ID, {
      type: 'vector',
      tiles: [`${API_BASE_URL}/api/v1/layers/land_price/tiles/{z}/{x}/{y}.pbf`],
      minzoom: 0,
      maxzoom: 18,
    });
  }

  if (!map.getLayer(LAND_PRICE_CASE_ID)) {
    map.addLayer({
      id: LAND_PRICE_CASE_ID,
      type: 'line',
      source: LAND_PRICE_SOURCE_ID,
      'source-layer': 'features',
      minzoom: 8,
      layout: { 'line-cap': 'round', 'line-join': 'round', visibility: enabled ? 'visible' : 'none' },
      paint: {
        'line-color': '#5b3415',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 2, 13, 5, 17, 9],
        'line-opacity': opacity,
      },
    });
  } else {
    map.setLayoutProperty(LAND_PRICE_CASE_ID, 'visibility', enabled ? 'visible' : 'none');
    map.setPaintProperty(LAND_PRICE_CASE_ID, 'line-opacity', opacity);
  }

  if (!map.getLayer(LAND_PRICE_LINE_ID)) {
    map.addLayer({
      id: LAND_PRICE_LINE_ID,
      type: 'line',
      source: LAND_PRICE_SOURCE_ID,
      'source-layer': 'features',
      minzoom: 8,
      layout: { 'line-cap': 'round', 'line-join': 'round', visibility: enabled ? 'visible' : 'none' },
      paint: {
        'line-color': '#f59e0b',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1, 13, 3, 17, 6],
        'line-opacity': opacity,
      },
    });
  } else {
    map.setLayoutProperty(LAND_PRICE_LINE_ID, 'visibility', enabled ? 'visible' : 'none');
    map.setPaintProperty(LAND_PRICE_LINE_ID, 'line-opacity', opacity);
  }
}

function currency(value: unknown) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? `${new Intl.NumberFormat('vi-VN').format(amount)} VND/m²`
    : 'Unavailable';
}

function popupContent(properties: Record<string, unknown>) {
  const root = document.createElement('section');
  root.className = 'land-price-popup';
  const title = document.createElement('strong');
  title.textContent = String(properties.road ?? 'Official An Khánh land reference price');
  root.append(title);

  const effectiveDate = document.createElement('p');
  effectiveDate.textContent = `Official reference price · effective ${String(properties.effective_from ?? 'date unavailable')}`;
  root.append(effectiveDate);

  const segment = document.createElement('p');
  segment.textContent = `${String(properties.start ?? '—')} → ${String(properties.end ?? '—')}`;
  root.append(segment);

  const prices = document.createElement('dl');
  const rows: Array<[string, string]> = [
    ['Residential', 'residential_vnd_m2'],
    ['Commercial', 'commercial_vnd_m2'],
    ['Other non-agricultural', 'other_nonagricultural_vnd_m2'],
  ];
  for (const [label, key] of rows) {
    const term = document.createElement('dt');
    term.textContent = label;
    const value = document.createElement('dd');
    value.textContent = currency(properties[key]);
    prices.append(term, value);
  }
  root.append(prices);

  const note = document.createElement('small');
  const coverage = properties.geometry_coverage;
  note.textContent = coverage === 'whole_named_road_proxy'
    ? 'Whole named-road geometry; price endpoints are not spatially clipped.'
    : 'Official reference price; see source attributes for coverage details.';
  root.append(note);

  if (typeof properties.source_url === 'string' && properties.source_url.startsWith('https://')) {
    const source = document.createElement('a');
    source.href = properties.source_url;
    source.target = '_blank';
    source.rel = 'noopener noreferrer';
    const page = properties.pdf_page ? ` · annex page ${String(properties.pdf_page)}` : '';
    source.textContent = `Open official source${page}`;
    root.append(source);
  }
  return root;
}

export function installLandPricePopup(
  map: MapLibreMap,
  popupConstructor: typeof import('maplibre-gl').Popup,
  interactive: () => boolean = () => true,
) {
  let popup: Popup | null = null;
  const click = (event: MapMouseEvent) => {
    if (!interactive()) return;
    if (!map.getLayer(LAND_PRICE_LINE_ID)) return;
    const feature = map.queryRenderedFeatures(event.point, { layers: [LAND_PRICE_LINE_ID] })[0];
    if (!feature) return;
    popup?.remove();
    // MapLibre feature properties are scalar values from the published snapshot.
    popup = new popupConstructor({ closeButton: true, closeOnClick: true, maxWidth: '320px' })
      .setLngLat(event.lngLat)
      .setDOMContent(popupContent(feature.properties ?? {}))
      .addTo(map);
  };
  const move = (event: MapMouseEvent) => {
    if (!interactive()) return;
    const hasPriceLine = map.getLayer(LAND_PRICE_LINE_ID)
      && map.queryRenderedFeatures(event.point, { layers: [LAND_PRICE_LINE_ID] }).length > 0;
    map.getCanvas().style.cursor = hasPriceLine ? 'pointer' : '';
  };
  const leave = () => { if (interactive()) map.getCanvas().style.cursor = ''; };
  map.on('click', click);
  map.on('mousemove', move);
  map.on('mouseout', leave);
  return () => {
    map.off('click', click);
    map.off('mousemove', move);
    map.off('mouseout', leave);
    popup?.remove();
  };
}
