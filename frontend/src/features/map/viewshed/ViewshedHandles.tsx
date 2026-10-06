import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { MeasurementProjection } from '../utils/measurementProjection';
import { readTerrainElevation } from '../utils/terrainElevation';
import {
  add,
  clamp,
  frame,
  frustumCorners,
  moveObserver,
  scale,
  type Vec3,
  type Viewshed,
} from './math';
import type { ViewshedAction, ViewshedState } from './state';
import { adjustHandle, dragPoint, handleAxis, type ViewshedHandle as Handle } from './manipulators';

interface Drag {
  view: Viewshed;
  handle: Handle;
  start: Vec3;
  ground: number | null;
  restore: () => void;
}

export function ViewshedHandles({
  map,
  projection,
  state,
  onAction,
}: {
  map: MapLibreMap;
  projection: MeasurementProjection;
  state: ViewshedState;
  onAction: (a: ViewshedAction) => void;
}) {
  const [, redraw] = useState(0),
    [active, setActive] = useState<Handle | null>(null),
    drag = useRef<Drag | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const render = () => redraw((v) => v + 1);
    map.on('render', render);
    return () => {
      map.off('render', render);
      drag.current?.restore();
    };
  }, [map]);
  const project = (view: Viewshed, p: Vec3) => {
    const geo = frame(view.observer).toGeo(p),
      m = projection.Mercator.fromLngLat([geo.longitude, geo.latitude], geo.elevationMeters);
    return projection.project(
      [m.x, m.y, m.z],
      map.getCanvas().clientWidth,
      map.getCanvas().clientHeight,
    );
  };
  const intersect = (view: Viewshed, handle: Handle, event: ReactPointerEvent) => {
    const rect = map.getCanvas().getBoundingClientRect();
    const ray = projection.ray(
      [event.clientX - rect.left, event.clientY - rect.top],
      rect.width,
      rect.height,
    );
    if (!ray) return null;
    const local = frame(view.observer);
    const convert = (p: Vec3) => {
      const m = new projection.Mercator(...p),
        ll = m.toLngLat();
      return local.toLocal({
        longitude: ll.lng,
        latitude: ll.lat,
        elevationMeters: m.toAltitude(),
      });
    };
    return dragPoint(
      convert(ray.near),
      convert(ray.far),
      handle.startsWith('observer') ? [0, 0, 0] : local.toLocal(view.target),
      handle,
      handleAxis(view, handle),
    );
  };
  const start = (event: ReactPointerEvent, view: Viewshed, handle: Handle) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    event.preventDefault();
    const p = intersect(view, handle, event);
    if (!p) return;
    const handlers = [
      map.dragPan,
      map.dragRotate,
      map.touchZoomRotate,
      map.doubleClickZoom,
      map.scrollZoom,
      map.touchPitch,
      map.keyboard,
    ];
    const enabled = handlers.map((h) => h.isEnabled());
    handlers.forEach((h) => h.disable());
    svg.current?.setPointerCapture(event.pointerId);
    drag.current = {
      view,
      handle,
      start: p,
      ground: readTerrainElevation(map, [view.observer.longitude, view.observer.latitude]),
      restore: () =>
        handlers.forEach((h, i) => {
          if (enabled[i]) h.enable();
        }),
    };
    setActive(handle);
  };
  const move = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    e.stopPropagation();
    e.preventDefault();
    const p = intersect(d.view, d.handle, e);
    if (!p) return;
    const delta = add(p, scale(d.start, -1)),
      local = frame(d.view.observer);
    let view: Viewshed;
    if (d.handle === 'observer-xy') {
      const point = local.toGeo([delta[0], delta[1], 0]),
        ground = readTerrainElevation(map, [point.longitude, point.latitude]);
      if (ground != null && d.ground != null) point.elevationMeters += ground - d.ground;
      view = moveObserver(d.view, point);
    } else if (d.handle === 'observer-z')
      view = moveObserver(d.view, {
        ...d.view.observer,
        elevationMeters: clamp(d.view.observer.elevationMeters + delta[2], -500, 9000),
      });
    else view = adjustHandle(d.view, d.handle, delta);
    onAction({ type: 'update', view });
  };
  const end = (e: ReactPointerEvent) => {
    if (!drag.current) return;
    e.stopPropagation();
    drag.current.restore();
    drag.current = null;
    setActive(null);
    if (svg.current?.hasPointerCapture(e.pointerId)) svg.current.releasePointerCapture(e.pointerId);
  };
  return (
    <svg
      className="viewshed-handles"
      ref={svg}
      aria-label="Viewshed spatial handles"
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={() => {
        drag.current?.restore();
        drag.current = null;
        setActive(null);
      }}
    >
      <defs>
        <marker
          id="viewshed-arrow"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L6,3 L0,6" fill="none" stroke="#f58220" strokeWidth="1.5" />
        </marker>
      </defs>
      {state.items.map((view) => {
        const o = project(view, [0, 0, 0]),
          corners = frustumCorners(view).map((p) => project(view, p));
        if (!o) return null;
        const selected = view.id === state.selectedId,
          editable = selected && state.phase === 'editing';
        const target = frame(view.observer).toLocal(view.target);
        const east = project(view, [1, 0, 0]),
          north = project(view, [0, 1, 0]);
        const pixelsPerMeter = Math.max(
          east ? Math.hypot(east.x - o.x, east.y - o.y) : 0,
          north ? Math.hypot(north.x - o.x, north.y - o.y) : 0,
          0.01,
        );
        const size = clamp(48 / pixelsPerMeter, 0.25, 200);
        const arrow = (handle: Handle, base: Vec3, axis: Vec3) => {
          const a = project(view, base),
            b = project(view, add(base, scale(axis, size)));
          if (!a || !b) return null;
          return (
            <g key={handle} className="viewshed-arrow-group" data-handle={handle}>
              <title>{handle.replace('-', ' ')}</title>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className={`viewshed-handle ${active === handle ? 'is-dragging' : ''}`}
                markerEnd="url(#viewshed-arrow)"
                onPointerDown={(e) => start(e, view, handle)}
              />
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className="viewshed-hit"
                onPointerDown={(e) => start(e, view, handle)}
              />
            </g>
          );
        };
        const circle = Array.from({ length: 33 }, (_, i) =>
          project(view, [
            Math.cos((i * Math.PI) / 16) * size * 0.3,
            Math.sin((i * Math.PI) / 16) * size * 0.3,
            0,
          ]),
        ).filter((p) => p != null);
        return (
          <g key={view.id}>
            {!['observer', 'target'].includes(state.phase) &&
              corners.map(
                (c, i) =>
                  c && (
                    <g
                      key={i}
                      onClick={(e) => {
                        e.stopPropagation();
                        onAction({ type: 'select', id: view.id });
                      }}
                    >
                      <line x1={o.x} y1={o.y} x2={c.x} y2={c.y} className="viewshed-hit" />
                      {corners[(i + 1) % 4] && (
                        <line
                          x1={c.x}
                          y1={c.y}
                          x2={corners[(i + 1) % 4]!.x}
                          y2={corners[(i + 1) % 4]!.y}
                          className="viewshed-hit"
                        />
                      )}
                    </g>
                  ),
              )}
            <circle
              cx={o.x}
              cy={o.y}
              r={6}
              className="viewshed-observer"
              style={{
                pointerEvents:
                  state.phase === 'target' || state.phase === 'observer' ? 'none' : undefined,
              }}
              role="button"
              tabIndex={state.phase === 'idle' || state.phase === 'editing' ? 0 : -1}
              aria-label={`Edit viewshed ${state.items.indexOf(view) + 1}`}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onAction({ type: 'select', id: view.id });
                }
              }}
              onClick={(e) => {
                e.stopPropagation();
                onAction({ type: 'select', id: view.id });
              }}
            >
              <title>Observer</title>
            </circle>
            {editable && (
              <>
                <g className="viewshed-disc-group">
                  <polyline
                    points={circle.map((p) => `${p.x},${p.y}`).join(' ')}
                    className={`viewshed-handle ${active === 'observer-xy' ? 'is-dragging' : ''}`}
                    onPointerDown={(e) => start(e, view, 'observer-xy')}
                  >
                    <title>Move observer horizontally</title>
                  </polyline>
                  <polyline
                    points={circle.map((p) => `${p.x},${p.y}`).join(' ')}
                    className="viewshed-hit"
                    onPointerDown={(e) => start(e, view, 'observer-xy')}
                  />
                </g>
                {(['fov-bottom', 'fov-right', 'fov-top', 'fov-left'] as const).map((handle, i) => {
                  const a = corners[i],
                    b = corners[(i + 1) % 4];
                  if (!a || !b) return null;
                  const label =
                    handle === 'fov-left' || handle === 'fov-right'
                      ? 'Horizontal FOV'
                      : 'Vertical FOV';
                  return (
                    <g
                      key={handle}
                      data-handle={handle}
                      className="viewshed-edge-group"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <title>{label} · drag to resize</title>
                      <line
                        x1={a.x}
                        y1={a.y}
                        x2={b.x}
                        y2={b.y}
                        className={`viewshed-handle viewshed-edge ${active === handle ? 'is-dragging' : ''}`}
                      />
                      <line
                        x1={a.x}
                        y1={a.y}
                        x2={b.x}
                        y2={b.y}
                        className="viewshed-hit"
                        onPointerDown={(e) => start(e, view, handle)}
                      />
                      <circle
                        cx={(a.x + b.x) / 2}
                        cy={(a.y + b.y) / 2}
                        r={5}
                        className="viewshed-edge-grip"
                        onPointerDown={(e) => start(e, view, handle)}
                      />
                    </g>
                  );
                })}
                {arrow('observer-z', [0, 0, 0], [0, 0, 1])}
                {arrow('heading', target, handleAxis(view, 'heading'))}
                {arrow('tilt', target, handleAxis(view, 'tilt'))}
                {arrow('distance', target, handleAxis(view, 'distance'))}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
