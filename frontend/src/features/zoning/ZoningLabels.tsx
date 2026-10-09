import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useState } from 'react';
import type { ZoningBridge } from './types';

export function ZoningLabels({ map, bridge }: { map: MapLibreMap | null; bridge: ZoningBridge }) {
  const [labels, setLabels] = useState<{ id: string; text: string; x: number; y: number }[]>([]);
  useEffect(() => {
    if (!map) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      if (!bridge.active || !bridge.visible || map.getZoom() < 13) { setLabels([]); return; }
      const cells = new Set<string>();
      const next = [];
      for (const zone of bridge.preview?.zones ?? bridge.scenario?.zones ?? []) {
        if (!zone.label_point || !map.getBounds().contains(zone.label_point)) continue;
        const p = map.project(zone.label_point), cell = `${Math.round(p.x / 80)},${Math.round(p.y / 35)}`;
        if (cells.has(cell)) continue;
        cells.add(cell);
        next.push({ id: zone.id, text: bridge.plan?.types.find(t => t.id === zone.type_id)?.code ?? 'Unknown', x: p.x, y: p.y });
        if (next.length >= 80) break;
      }
      setLabels(next);
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    schedule(); map.on('move', schedule); map.on('resize', schedule);
    return () => { cancelAnimationFrame(frame); map.off('move', schedule); map.off('resize', schedule); };
  }, [map, bridge.active, bridge.visible, bridge.preview, bridge.scenario, bridge.plan]);
  if (!bridge.active || !bridge.visible) return null;
  return <div className="zoning-map-labels" aria-hidden="true">{labels.map(label => <span key={label.id} style={{ transform: `translate(${label.x}px, ${label.y}px) translate(-50%, -50%)` }}>{label.text}</span>)}</div>;
}
