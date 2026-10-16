import { useEffect } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { API_BASE_URL } from '../../services/api';
import { PARCEL_MAX_NATIVE_ZOOM, PARCEL_MIN_ZOOM, parcelFill, parcelOutline } from '../map/datasets/parcelStyle';
import type { Plan, ZoningBridge } from './types';

function PlanParcels({ map, plan }: { map: MapLibreMap; plan: Plan }) {
  useEffect(() => {
    const source = `zoning-preview-parcels-${plan.id}`;
    const fill = `${source}-fill`, outline = `${source}-outline`;
    const attach = () => {
      if (!map.getSource(source)) map.addSource(source, { type: 'vector',
        tiles: [`${API_BASE_URL}/api/v1/zoning/plans/${encodeURIComponent(plan.id)}/parcels/tiles/{z}/{x}/{y}.pbf?revision=${plan.revision}&schema=2`],
        minzoom: PARCEL_MIN_ZOOM, maxzoom: PARCEL_MAX_NATIVE_ZOOM });
      const before = map.getLayer('zoning-fill') ? 'zoning-fill' : undefined;
      if (!map.getLayer(fill)) map.addLayer({ ...parcelFill(), id: fill, source,
        paint: { ...parcelFill().paint, 'fill-opacity': .44 } }, before);
      if (!map.getLayer(outline)) map.addLayer({ ...parcelOutline(), id: outline, source,
        paint: { ...parcelOutline().paint, 'line-color': '#005b65', 'line-opacity': .9 } }, before);
    };
    if (map.isStyleLoaded()) attach();
    map.on('style.load', attach);
    map.on('idle', attach);
    return () => {
      map.off('style.load', attach);
      map.off('idle', attach);
      if (map.getLayer(outline)) map.removeLayer(outline);
      if (map.getLayer(fill)) map.removeLayer(fill);
      if (map.getSource(source)) map.removeSource(source);
    };
  }, [map, plan.id, plan.revision]);
  return null;
}

export function DisplayedPlanParcelsScene({ map, bridge }: { map: MapLibreMap | null; bridge: ZoningBridge }) {
  if (!map || !bridge.active || !bridge.parcelAvailable || bridge.plan) return null;
  return <>{bridge.displayedPlanScenes?.map(({ plan }) => <PlanParcels key={plan.id} map={map} plan={plan}/>)}</>;
}
