import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson';
import { useEffect, useRef } from 'react';
import { editVertex, rings, sketchGeometry } from './geometry';
import type { PolygonGeometry, ZoningBridge } from './types';

const SOURCE = 'zoning-editor';
const FILL = 'zoning-fill', LINE = 'zoning-outline', VERTEX = 'zoning-vertices';
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
function feature(geometry: Geometry, properties: Record<string, unknown>): Feature { return { type: 'Feature', geometry, properties }; }

function data(bridge: ZoningBridge): FeatureCollection {
  if (!bridge.active) return EMPTY;
  const features: Feature[] = [];
  if (bridge.plan) features.push(feature(bridge.plan.study_area, { kind: 'study', color: '#005b65', alpha: 0, width: 3 }));
  if (bridge.visible) for (const zone of bridge.preview?.zones ?? bridge.scenario?.zones ?? []) {
    const type = bridge.plan?.types.find(t => t.id === zone.type_id);
    features.push(feature(zone.geometry, { kind: 'zone', id: zone.id, label: type?.code ?? 'Unknown',
      color: type?.color ?? '#6d8588', alpha: bridge.opacity, width: bridge.selected.includes(zone.id) ? 4 : 1.5 }));
  }
  const draft = sketchGeometry(bridge.sketch);
  if (draft) features.push(feature(draft, { kind: 'draft', color: '#005b65', alpha: .18, width: 3 }));
  else if (bridge.sketch.points.length > 1) features.push(feature({ type: 'LineString', coordinates: bridge.sketch.points },
    { kind: 'draft', color: '#005b65', alpha: 0, width: 3 }));
  const editableRings = bridge.sketch.geometry && bridge.sketch.geometry.type !== 'LineString'
    ? rings(bridge.sketch.geometry).map(r => r.slice(0, -1)) : [bridge.sketch.points];
  editableRings.forEach((ring, r) => ring.forEach((point, i) => {
    features.push(feature({ type: 'Point', coordinates: point }, { kind: 'vertex', ring: r, index: i, color: '#005b65' }));
    if (bridge.sketch.geometry && bridge.sketch.geometry.type !== 'LineString') {
      const next = ring[(i + 1) % ring.length];
      features.push(feature({ type: 'Point', coordinates: [(point[0] + next[0]) / 2, (point[1] + next[1]) / 2] },
        { kind: 'midpoint', ring: r, index: i, color: '#ffffff' }));
    }
  }));
  return { type: 'FeatureCollection', features };
}

export function ZoningScene({ map, bridge }: { map: MapLibreMap | null; bridge: ZoningBridge }) {
  const current = useRef(bridge);
  useEffect(() => { current.current = bridge; }, [bridge]);
  useEffect(() => {
    if (!map || !bridge.active) return;
    let dragging: { ring: number; index: number; restorePan: boolean } | null = null;
    let suppressClick = false;
    let releaseFrame = 0;
    const doubleClick = map.doubleClickZoom.isEnabled();
    const boxZoom = map.boxZoom.isEnabled();
    map.doubleClickZoom.disable();
    map.boxZoom.disable(); // Shift-click belongs to multi-selection while the editor owns input.
    const attach = () => {
      if (!map.getSource(SOURCE)) map.addSource(SOURCE, { type: 'geojson', data: data(current.current) });
      if (!map.getLayer(FILL)) map.addLayer({ id: FILL, source: SOURCE, type: 'fill', filter: ['==', '$type', 'Polygon'],
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': ['get', 'alpha'] } });
      if (!map.getLayer(LINE)) map.addLayer({ id: LINE, source: SOURCE, type: 'line', filter: ['!=', '$type', 'Point'],
        paint: { 'line-color': ['get', 'color'], 'line-width': ['get', 'width'] } });
      if (!map.getLayer(VERTEX)) map.addLayer({ id: VERTEX, source: SOURCE, type: 'circle', filter: ['==', '$type', 'Point'],
        paint: { 'circle-color': ['get', 'color'], 'circle-radius': 5, 'circle-stroke-color': '#005b65', 'circle-stroke-width': 2 } });
    };
    const query = (e: MapMouseEvent, layer: string) => map.getLayer(layer) ? map.queryRenderedFeatures(e.point, { layers: [layer] }) : [];
    const snap = (e: MapMouseEvent): Position => {
      const candidates = current.current.plan ? rings(current.current.plan.study_area).flat() : [];
      for (const z of current.current.scenario?.zones ?? []) candidates.push(...rings(z.geometry).flat());
      let closest: Position = [e.lngLat.lng, e.lngLat.lat], distance = 8;
      for (const position of candidates) {
        const p = map.project([position[0], position[1]]), d = Math.hypot(p.x - e.point.x, p.y - e.point.y);
        if (d < distance) { distance = d; closest = position; }
      }
      return closest;
    };
    const click = (e: MapMouseEvent) => {
      const b = current.current;
      if (!b.active || b.busy) return;
      if (suppressClick) { suppressClick = false; return; }
      const handle = query(e, VERTEX)[0];
      if (b.sketch.geometry && b.sketch.geometry.type !== 'LineString') {
        if (handle) {
          const { ring, index, kind } = handle.properties;
          const insert = kind === 'midpoint';
          if (insert || e.originalEvent.shiftKey) b.onSketch({ ...b.sketch,
            geometry: editVertex(b.sketch.geometry, Number(ring), Number(index), insert ? snap(e) : null, insert) });
        }
        return;
      }
      if (b.sketch.tool) {
        if (b.sketch.points.length < 1000) b.onSketch({ ...b.sketch, points: [...b.sketch.points, snap(e)] });
        return;
      }
      const picked = query(e, FILL).find(f => f.properties.kind === 'zone');
      b.onPick(picked ? String(picked.properties.id) : null, e.originalEvent.shiftKey);
    };
    const down = (e: MapMouseEvent) => {
      const b = current.current, handle = query(e, VERTEX)[0];
      if (!b.active || b.busy || !b.sketch.geometry || b.sketch.geometry.type === 'LineString' || !handle ||
        handle.properties.kind !== 'vertex' || e.originalEvent.shiftKey) return;
      e.preventDefault();
      dragging = { ring: Number(handle.properties.ring), index: Number(handle.properties.index), restorePan: map.dragPan.isEnabled() };
      map.dragPan.disable();
    };
    const move = (e: MapMouseEvent) => {
      const b = current.current;
      if (!dragging || !b.sketch.geometry || b.sketch.geometry.type === 'LineString') return;
      suppressClick = true;
      const sketch = { ...b.sketch, geometry: editVertex(b.sketch.geometry, dragging.ring, dragging.index, snap(e)) };
      current.current = { ...b, sketch }; // Keep fast pointer moves independent of React's render cadence.
      b.onSketch(sketch);
    };
    const up = () => {
      if (!dragging) return;
      if (dragging.restorePan) map.dragPan.enable();
      dragging = null;
      // Suppress only the synthetic click from this drag, not the next edit tool's click.
      cancelAnimationFrame(releaseFrame);
      releaseFrame = requestAnimationFrame(() => { suppressClick = false; });
    };
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest('input, textarea, select, button, dialog') || current.current.busy) return;
      if (e.key === 'Escape') current.current.onCancel();
      if (e.key === 'Enter' && current.current.sketch.tool) { e.preventDefault(); current.current.onFinish(); }
      if (e.key === 'Backspace' && current.current.sketch.tool && !current.current.sketch.geometry) {
        e.preventDefault(); current.current.onSketch({ ...current.current.sketch, points: current.current.sketch.points.slice(0, -1) });
      }
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach); map.on('click', click); map.on('mousedown', down); map.on('mousemove', move); map.on('mouseup', up);
    window.addEventListener('mouseup', up); window.addEventListener('keydown', key);
    return () => {
      up(); cancelAnimationFrame(releaseFrame); if (doubleClick) map.doubleClickZoom.enable();
      if (boxZoom) map.boxZoom.enable();
      map.off('style.load', attach); map.off('click', click); map.off('mousedown', down); map.off('mousemove', move); map.off('mouseup', up);
      window.removeEventListener('mouseup', up); window.removeEventListener('keydown', key);
      for (const id of [VERTEX, LINE, FILL]) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);
      map.getCanvas().style.cursor = '';
    };
  }, [map, bridge.active]);

  useEffect(() => {
    if (!map) return;
    (map.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(data(bridge));
    if (bridge.active) map.getCanvas().style.cursor = bridge.sketch.tool ? 'crosshair' : '';
  }, [map, bridge]);

  useEffect(() => {
    if (!map || !bridge.focus) return;
    const points = rings(bridge.focus.geometry as PolygonGeometry).flat();
    const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    const width = map.getContainer().clientWidth;
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], {
      padding: width > 900 ? { left: 410, right: 100, top: 140, bottom: 300 } : 80,
      maxZoom: 18, duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 600,
    });
  }, [map, bridge.focus]);
  return null;
}
