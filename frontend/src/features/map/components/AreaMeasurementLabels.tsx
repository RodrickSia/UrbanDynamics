import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { gsap, motionDuration, useGSAP } from '../motion';
import type { MapMode, MeasurementState } from '../types/map';
import { calculateAreaMeasurement } from '../utils/measurementArea';
import { formatArea, formatLength } from '../utils/measurementUnits';
import type { MeasurementProjection } from '../utils/measurementProjection';

export function AreaMeasurementLabels({ map, projection, measurement, mode }: {
  map: MapLibreMap | null; projection: MeasurementProjection | null;
  measurement: MeasurementState; mode: MapMode;
}) {
  const area = useMemo(() => calculateAreaMeasurement(measurement.status === 'active' && measurement.preview
    ? [...measurement.points,measurement.preview] : measurement.points,mode), [measurement,mode]);
  const areaRef = useRef(area);
  const elementsRef = useRef(new Map<string,HTMLDivElement>());
  const updateRef = useRef(() => {});
  useEffect(() => {
    if (!map || !projection) return;
    const update = () => {
      const current = areaRef.current, canvas = map.getCanvas();
      for (const [id,anchor] of [['area',current.areaAnchor],['perimeter',current.perimeterAnchor]] as const) {
        const element = elementsRef.current.get(id);
        if (!element || !anchor) continue;
        const p = projection.Mercator.fromLngLat([anchor.longitude,anchor.latitude], mode === '3d' ? anchor.elevationMeters : 0);
        const screen = projection.project([p.x,p.y,p.z],canvas.clientWidth,canvas.clientHeight);
        element.style.visibility = screen?.visible ? 'visible' : 'hidden';
        if (screen?.visible) element.style.transform = `translate3d(${screen.x}px,${screen.y}px,0)`;
      }
    };
    updateRef.current = update;
    map.on('render',update); map.triggerRepaint(); update();
    return () => { map.off('render',update); updateRef.current = () => {}; };
  }, [map,projection,mode]);
  useLayoutEffect(() => { areaRef.current = area; updateRef.current(); map?.triggerRepaint(); }, [area,map]);
  if (!area.valid) return null;
  const units = measurement.units ?? 'metric';
  return <div className="measurement-label-layer" aria-hidden="true">
    {(['area','perimeter'] as const).map(id => <div key={id} className={`measurement-label-anchor area-label-${id}`}
      data-area-label={id} ref={element => { if (element) elementsRef.current.set(id,element); else elementsRef.current.delete(id); }}>
      <span className="measurement-label-position"><AreaPill preview={measurement.status === 'active'}>
        {id === 'area' ? formatArea(area.areaSquareMeters,units) : `Perimeter ${formatLength(area.perimeterMeters,units)}`}
      </AreaPill></span>
    </div>)}
  </div>;
}

function AreaPill({ children,preview }: { children: string; preview: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useGSAP(() => {
    gsap.fromTo(ref.current,{ autoAlpha:0,scale:0.88,y:5 }, { autoAlpha:1,scale:1,y:0,
      duration:motionDuration(0.28),ease:'back.out(1.3)',clearProps:'transform,opacity,visibility' });
  }, { scope:ref });
  return <span ref={ref} className={`measurement-distance-pill${preview ? ' is-preview' : ''}`}>{children}</span>;
}
