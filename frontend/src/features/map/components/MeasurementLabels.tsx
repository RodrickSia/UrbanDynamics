import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';

import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapMode, MeasurementState } from '../types/map';
import {
  createMeasurementDistanceLabels,
  formatMeasurementDistance,
  type MeasurementDistanceLabel,
} from '../utils/measurement';
import type { MeasurementProjection, Position3 } from '../utils/measurementProjection';

interface MeasurementLabelsProps {
  map: MapLibreMap | null;
  projection: MeasurementProjection | null;
  measurement: MeasurementState;
  mode: MapMode;
}

export function MeasurementLabels({ map, projection, measurement, mode }: MeasurementLabelsProps) {
  const labels = useMemo(
    () => createMeasurementDistanceLabels(measurement, mode),
    [measurement, mode],
  );
  const labelsRef = useRef(labels);
  const elementsRef = useRef(new Map<string, HTMLDivElement>());
  const updateRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (!map || !projection) return;
    const update = () => {
      const canvas = map.getCanvas();
      for (const label of labelsRef.current) {
        const element = elementsRef.current.get(label.id);
        if (!element) continue;
        const start = projection.Mercator.fromLngLat(
          [label.start.longitude, label.start.latitude],
          mode === '3d' ? label.start.elevationMeters : 0,
        );
        const end = projection.Mercator.fromLngLat(
          [label.end.longitude, label.end.latitude],
          mode === '3d' ? label.end.elevationMeters : 0,
        );
        const midpoint: Position3 = [
          (start.x + end.x) / 2,
          (start.y + end.y) / 2,
          (start.z + end.z) / 2,
        ];
        const position = projection.project(midpoint, canvas.clientWidth, canvas.clientHeight);
        element.style.visibility = position?.visible ? 'visible' : 'hidden';
        if (position?.visible) {
          const a = projection.project([start.x, start.y, start.z], canvas.clientWidth, canvas.clientHeight);
          const b = projection.project([end.x, end.y, end.z], canvas.clientWidth, canvas.clientHeight);
          if (a && b && Math.hypot(a.x - b.x, a.y - b.y) < 80) {
            // Shift short-segment labels away from the endpoints, especially
            // vertical edges whose midpoint pill would otherwise cover them.
            if (Math.abs(a.y - b.y) > Math.abs(a.x - b.x)) position.x += 42;
            else position.y -= 12;
          }
          element.style.transform = `translate3d(${position.x}px, ${position.y}px, 0)`;
        }
      }
    };
    updateRef.current = update;
    map.on('render', update);
    map.triggerRepaint();
    update();
    return () => {
      map.off('render', update);
      updateRef.current = () => undefined;
    };
  }, [map, mode, projection]);

  useLayoutEffect(() => {
    labelsRef.current = labels;
    updateRef.current();
    map?.triggerRepaint();
  }, [labels, map]);

  if (labels.length === 0) return null;
  return (
    <div className="measurement-label-layer" aria-hidden="true">
      {labels.map((label) => (
        <MeasurementDistancePill
          key={label.id}
          label={label}
          register={(element) => {
            if (element) elementsRef.current.set(label.id, element);
            else elementsRef.current.delete(label.id);
          }}
        />
      ))}
    </div>
  );
}

function MeasurementDistancePill({
  label,
  register,
}: {
  label: MeasurementDistanceLabel;
  register: (element: HTMLDivElement | null) => void;
}) {
  const pillRef = useRef<HTMLSpanElement>(null);
  useGSAP(() => {
    gsap.fromTo(
      pillRef.current,
      { autoAlpha: 0, scale: 0.84, y: 6 },
      {
        autoAlpha: 1,
        scale: 1,
        y: 0,
        duration: motionDuration(0.28),
        ease: 'back.out(1.45)',
        clearProps: 'transform,opacity,visibility',
      },
    );
  }, { scope: pillRef });

  return (
    <div ref={register} className="measurement-label-anchor">
      <span className="measurement-label-position">
        <span
          ref={pillRef}
          className={`measurement-distance-pill${label.preview ? ' is-preview' : ''}`}
        >
          {label.distanceMeters == null
            ? 'Elevation unavailable'
            : `${label.component ? `${label.component} ` : ''}${formatMeasurementDistance(label.distanceMeters)}`}
        </span>
      </span>
    </div>
  );
}
