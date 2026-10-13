import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson';
import { useEffect, useRef } from 'react';
import { API_BASE_URL } from '../../services/api';
import { PARCEL_MAX_NATIVE_ZOOM, PARCEL_MIN_ZOOM, parcelOutline } from '../map/datasets/parcelStyle';
import { editVertex, rings, sketchGeometry } from './geometry';
import { nearestSnap, snapSource, type SnapGeometry } from './snapping';
import type { PolygonGeometry, ZoningBridge } from './types';
import { BUILDING_LAYER, BUILDING_EXCLUDED_LAYER, BUILDING_FOOTPRINT_LAYER } from './DevelopmentScene';

const SOURCE = 'zoning-editor';
const FILL = 'zoning-fill', LINE = 'zoning-outline', VERTEX = 'zoning-vertices';
const PARCEL_SOURCE = 'zoning-plan-parcels';
const PARCEL_LINE = 'zoning-plan-parcels-outline';
const PARCEL_PICK = 'zoning-plan-parcels-pick';
const PARCEL_FILL = 'zoning-plan-parcels-fill';
const SNAP_SOURCE = 'zoning-snap-point', SNAP_LAYER = 'zoning-snap-indicator';
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const DRAW_COLOR = '#FF6D00';
function feature(geometry: Geometry, properties: Record<string, unknown>): Feature { return { type: 'Feature', geometry, properties }; }

function data(bridge: ZoningBridge): FeatureCollection {
  if (!bridge.active) return EMPTY;
  const features: Feature[] = [];
  if (bridge.plan) features.push(feature(bridge.plan.study_area, { kind: 'study', color: '#005b65', alpha: 0, width: 3 }));
  if (bridge.visible) for (const zone of bridge.scenario?.zones ?? []) {
    const type = bridge.plan?.types.find(t => t.id === zone.type_id);
    features.push(feature(zone.geometry, { kind: 'zone', id: zone.id, label: type?.code ?? 'Unknown',
      color: type?.color ?? '#6d8588', alpha: bridge.sketch.tool ? 0 : bridge.opacity,
      width: bridge.selected.includes(zone.id) ? 4 : 1.5 }));
  }
  const draft = sketchGeometry(bridge.sketch);
  if (draft) features.push(feature(draft, { kind: 'draft', color: DRAW_COLOR, alpha: 0, width: 3 }));
  else if (bridge.sketch.points.length > 1) features.push(feature({ type: 'LineString', coordinates: bridge.sketch.points },
    { kind: 'draft', color: DRAW_COLOR, alpha: 0, width: 3 }));
  const editableRings = bridge.sketch.geometry && bridge.sketch.geometry.type !== 'LineString'
    ? rings(bridge.sketch.geometry).map(r => r.slice(0, -1)) : [bridge.sketch.points];
  editableRings.forEach((ring, r) => ring.forEach((point, i) => {
    features.push(feature({ type: 'Point', coordinates: point }, { kind: 'vertex', ring: r, index: i, color: DRAW_COLOR }));
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
  const parcelTiles = bridge.plan
    ? `${API_BASE_URL}/api/v1/zoning/plans/${encodeURIComponent(bridge.plan.id)}/parcels/tiles/{z}/{x}/{y}.pbf?revision=${bridge.plan.revision}&schema=2`
    : `${API_BASE_URL}/api/v1/layers/parcels/tiles/{z}/{x}/{y}.pbf?schema=2`;
  useEffect(() => { current.current = bridge; }, [bridge]);
  useEffect(() => {
    if (!map || !bridge.active) return;
    let dragging: { ring: number; index: number; restorePan: boolean } | null = null;
    let suppressClick = false;
    let releaseFrame = 0;
    let snapFrame = 0;
    let pendingSnap: MapMouseEvent | null = null;
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
        paint: { 'circle-color': ['get', 'color'], 'circle-radius': 5, 'circle-stroke-color': DRAW_COLOR, 'circle-stroke-width': 2 } });
      if (!map.getSource(SNAP_SOURCE)) map.addSource(SNAP_SOURCE, { type: 'geojson', data: EMPTY });
      if (!map.getLayer(SNAP_LAYER)) map.addLayer({ id: SNAP_LAYER, source: SNAP_SOURCE, type: 'circle',
        paint: { 'circle-radius': 6, 'circle-color': '#fff', 'circle-stroke-color': DRAW_COLOR, 'circle-stroke-width': 2.5 } });
    };
    const query = (e: MapMouseEvent, layer: string) => map.getLayer(layer) ? map.queryRenderedFeatures(e.point, { layers: [layer] }) : [];
    const snapCandidate = (e: MapMouseEvent) => {
      if (e.originalEvent.ctrlKey) return null;
      const candidates: SnapGeometry[] = [];
      if (current.current.plan) candidates.push({ geometry: current.current.plan.study_area, source: 'zoning' });
      if (current.current.development?.parcel) candidates.push({ geometry: current.current.development.parcel.geometry, source: 'parcel' });
      for (const zone of current.current.scenario?.zones ?? []) candidates.push({ geometry: zone.geometry, source: 'zoning' });
      const layers = map.getStyle().layers.filter(layer =>
        layer.id === PARCEL_LINE ? current.current.showParcels : snapSource(layer) !== null);
      if (layers.length) {
        const { x, y } = e.point;
        const features = map.queryRenderedFeatures([[x - 10, y - 10], [x + 10, y + 10]],
          { layers: layers.map(layer => layer.id) }).slice(0, 40);
        for (const item of features) {
          const source = snapSource(item.layer);
          if (source) candidates.push({ geometry: item.geometry, source });
        }
      }
      return nearestSnap(e.point, candidates, position => map.project([position[0], position[1]]), 10);
    };
    const snap = (e: MapMouseEvent): Position => snapCandidate(e)?.coordinate ?? [e.lngLat.lng, e.lngLat.lat];
    const showSnap = (e: MapMouseEvent) => {
      const source = map.getSource(SNAP_SOURCE) as GeoJSONSource | undefined;
      if (!source) return;
      const candidate = current.current.sketch.tool ? snapCandidate(e) : null;
      source.setData(candidate ? { type: 'FeatureCollection',
        features: [feature({ type: 'Point', coordinates: candidate.coordinate }, {})] } : EMPTY);
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
      if (b.development?.active) {
        const building = query(e, BUILDING_LAYER)[0] ?? query(e, BUILDING_EXCLUDED_LAYER)[0] ?? query(e, BUILDING_FOOTPRINT_LAYER)[0];
        if (building && building.properties.id !== 'preview') b.development.onPickBuilding(String(building.properties.id));
        else {
          const parcel = query(e, PARCEL_PICK)[0];
          const id = parcel?.properties.parcel_id ?? parcel?.id;
          if (id !== undefined) b.development.onPickParcel(String(id));
        }
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
      pendingSnap = e;
      if (current.current.sketch.tool && !snapFrame) {
        snapFrame = requestAnimationFrame(() => { snapFrame = 0; if (pendingSnap) showSnap(pendingSnap); });
      }
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
      if (e.key === 'Control') (map.getSource(SNAP_SOURCE) as GeoJSONSource | undefined)?.setData(EMPTY);
      if (current.current.development?.active && e.key === 'Delete' && !current.current.sketch.tool) {
        e.preventDefault(); current.current.development.onDelete();
      }
      if (current.current.development?.active && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (current.current.sketch.tool && !current.current.sketch.geometry) current.current.onSketch({
          ...current.current.sketch, points: current.current.sketch.points.slice(0, -1) });
        else if (!current.current.sketch.tool) current.current.development.onUndo(e.shiftKey);
      }
      if (e.key === 'Escape') current.current.onCancel();
      if (e.key === 'Enter' && current.current.sketch.tool) { e.preventDefault(); current.current.onFinish(); }
      if (e.key === 'Backspace' && current.current.sketch.tool && !current.current.sketch.geometry) {
        e.preventDefault(); current.current.onSketch({ ...current.current.sketch, points: current.current.sketch.points.slice(0, -1) });
      }
    };
    if (map.isStyleLoaded()) attach();
    // Opening a plan while vector tiles load can miss style.load, which has
    // already fired. Attach the editor on idle as well so handles stay available.
    map.on('style.load', attach); map.on('idle', attach); map.on('click', click); map.on('mousedown', down); map.on('mousemove', move); map.on('mouseup', up);
    window.addEventListener('mouseup', up); window.addEventListener('keydown', key);
    return () => {
      up(); cancelAnimationFrame(releaseFrame); cancelAnimationFrame(snapFrame); if (doubleClick) map.doubleClickZoom.enable();
      if (boxZoom) map.boxZoom.enable();
      map.off('style.load', attach); map.off('idle', attach); map.off('click', click); map.off('mousedown', down); map.off('mousemove', move); map.off('mouseup', up);
      window.removeEventListener('mouseup', up); window.removeEventListener('keydown', key);
      for (const id of [SNAP_LAYER, VERTEX, LINE, FILL]) if (map.getLayer(id)) map.removeLayer(id);
      for (const id of [SNAP_SOURCE, SOURCE]) if (map.getSource(id)) map.removeSource(id);
      map.getCanvas().style.cursor = '';
    };
  }, [map, bridge.active]);

  useEffect(() => {
    if (!map || !bridge.active || !bridge.parcelAvailable || (!bridge.plan && bridge.sketch.tool !== 'study')) return;
    const attach = () => {
      if (!map.getSource(PARCEL_SOURCE)) map.addSource(PARCEL_SOURCE, { type: 'vector', tiles: [parcelTiles],
        minzoom: PARCEL_MIN_ZOOM, maxzoom: PARCEL_MAX_NATIVE_ZOOM });
      if (!map.getLayer(PARCEL_LINE)) map.addLayer({ ...parcelOutline(), id: PARCEL_LINE, source: PARCEL_SOURCE,
        paint: { ...parcelOutline().paint, 'line-color': '#005b65', 'line-opacity': current.current.showParcels ? .9 : 0 } });
      if (!map.getLayer(PARCEL_PICK)) map.addLayer({ id: PARCEL_PICK, source: PARCEL_SOURCE, 'source-layer': 'features',
        type: 'fill', paint: { 'fill-opacity': 0 } }, PARCEL_LINE);
      if (current.current.plan && !map.getLayer(PARCEL_FILL)) map.addLayer({ id: PARCEL_FILL,
        source: PARCEL_SOURCE, 'source-layer': 'features', type: 'fill', minzoom: PARCEL_MIN_ZOOM,
        paint: { 'fill-color': ['to-color', ['get', 'color'], '#94a3b8'], 'fill-opacity': .35,
          'fill-antialias': false } }, map.getLayer(FILL) ? FILL : PARCEL_LINE);
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach);
    map.on('idle', attach);
    return () => {
      map.off('style.load', attach);
      map.off('idle', attach);
      if (map.getLayer(PARCEL_PICK)) map.removeLayer(PARCEL_PICK);
      if (map.getLayer(PARCEL_FILL)) map.removeLayer(PARCEL_FILL);
      if (map.getLayer(PARCEL_LINE)) map.removeLayer(PARCEL_LINE);
      if (map.getSource(PARCEL_SOURCE)) map.removeSource(PARCEL_SOURCE);
    };
  }, [map, bridge.active, bridge.parcelAvailable, bridge.plan, bridge.sketch.tool, parcelTiles]);

  useEffect(() => {
    if (!map) return;
    if (map.getLayer(PARCEL_LINE)) map.setPaintProperty(PARCEL_LINE, 'line-opacity', bridge.showParcels ? .9 : 0);
  }, [map, bridge.showParcels, bridge.plan?.id, bridge.plan?.revision]);

  useEffect(() => {
    if (!map) return;
    (map.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(data(bridge));
    if (!bridge.sketch.tool) (map.getSource(SNAP_SOURCE) as GeoJSONSource | undefined)?.setData(EMPTY);
    if (bridge.active) map.getCanvas().style.cursor = bridge.sketch.tool ? 'crosshair' : '';
  }, [map, bridge]);

  useEffect(() => {
    if (!map || !bridge.focus) return;
    const points = rings(bridge.focus.geometry as PolygonGeometry).flat();
    const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
    const width = map.getContainer().clientWidth;
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], {
      padding: width > 900 ? { left: 100, right: 410, top: 140, bottom: 300 } : 80,
      maxZoom: 18, duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 600,
    });
  }, [map, bridge.focus]);
  return null;
}
