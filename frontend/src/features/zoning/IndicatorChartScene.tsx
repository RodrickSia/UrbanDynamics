import { useEffect, useMemo, useRef } from 'react';
import type { Popup, GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { chartFeatures } from './indicatorChart';
import type { ZoningBridge } from './types';

const SOURCE = 'indicator-chart', BARS = 'indicator-chart-bars', BASE = 'indicator-chart-base';
export function IndicatorChartScene({ map, bridge, mode }: { map: MapLibreMap | null; bridge: ZoningBridge; mode: '2d' | '3d' }) {
  const chart = bridge.active && bridge.analysis?.active ? bridge.analysis.chart : undefined;
  const data = useMemo(() => chart ? chartFeatures(chart.geometry, chart.rows) : null, [chart]);
  const enabled = !!data;
  const current = useRef({ data });
  useEffect(() => {
    current.current = { data };
    const source = map?.getSource(SOURCE) as GeoJSONSource | undefined;
    source?.setData(data ?? { type: 'FeatureCollection', features: [] });
    if (map?.getLayer(BARS)) map.setLayoutProperty(BARS, 'visibility', 'visible');
  }, [map, data]);
  useEffect(() => {
    if (!map || !enabled || mode !== '2d') return;
    const showColumns = () => { if (map.getPitch() < 40) map.easeTo({ pitch: 50, duration: 420 }); };
    showColumns();
    // A global 2D camera transition may finish after the chart is enabled.
    map.on('moveend', showColumns);
    return () => {
      map.off('moveend', showColumns);
      if (map.getPitch() >= 40) map.easeTo({ pitch: 0, duration: 350 });
    };
  }, [map, enabled, mode]);
  useEffect(() => {
    if (!map || !enabled) return;
    const attach = () => {
      if (!map.getSource(SOURCE)) map.addSource(SOURCE, { type: 'geojson', data: current.current.data! });
      if (!map.getLayer(BASE)) map.addLayer({ id: BASE, type: 'fill', source: SOURCE,
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': .8 } });
      if (!map.getLayer(BARS)) map.addLayer({ id: BARS, type: 'fill-extrusion', source: SOURCE,
        layout: { visibility: 'visible' },
        paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-opacity': .94 } });
    };
    let popup: Popup | undefined, disposed = false;
    void import('maplibre-gl').then(({ Popup }) => {
      if (!disposed) popup = new Popup({ closeButton: false, closeOnClick: false, maxWidth: '260px' });
    });
    const hover = (event: MapMouseEvent) => {
      const layers = [BARS, BASE].filter(id => map.getLayer(id));
      const feature = layers.length ? map.queryRenderedFeatures(event.point, { layers })[0] : undefined;
      if (feature) popup?.setLngLat(event.lngLat).setText(String(feature.properties.label)).addTo(map);
      else popup?.remove();
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach); map.on('idle', attach); map.on('mousemove', hover);
    return () => {
      disposed = true; popup?.remove(); map.off('style.load', attach); map.off('idle', attach); map.off('mousemove', hover);
      for (const id of [BARS, BASE]) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
    };
    // Refresh data separately to retain layers across metric and camera changes.
  }, [map, enabled]);
  return null;
}
