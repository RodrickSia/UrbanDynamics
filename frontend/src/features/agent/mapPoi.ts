import type { Map as MapLibreMap } from 'maplibre-gl';
import { isPoiLayer } from '../map/layers/poi';

export type MapPoiSnapshot = {
  type:'FeatureCollection'; features:import('geojson').Feature<import('geojson').Point>[];
  bbox:number[]; zoom:number; captured_at:string; source:string;
};

/** Query the system's existing POI vector source, including provider-hidden labels.
 * Loaded tiles are a bounded view, never an exhaustive POI database.
 */
export function mapPoiSnapshot(map:MapLibreMap):MapPoiSnapshot {
  const bounds=map.getBounds(),seen=new Set<string>(),groups=new Set<string>();
  const features:MapPoiSnapshot['features']=[];
  for(const layer of map.getStyle().layers??[]){
    if(!isPoiLayer(layer)||!('source' in layer)||typeof layer.source!=='string'||!('source-layer' in layer)||!layer['source-layer'])continue;
    const sourceLayer=layer['source-layer'],group=layer.source+'|'+sourceLayer;
    if(groups.has(group))continue;groups.add(group);
    for(const feature of map.querySourceFeatures(layer.source,{sourceLayer})){
      if(feature.geometry.type!=='Point')continue;
      const [lng,lat]=feature.geometry.coordinates;
      if(!bounds.contains([lng,lat]))continue;
      const properties:Record<string,string|number|boolean>={};
      for(const [key,value] of Object.entries(feature.properties??{}).slice(0,30)){
        if(typeof value==='string')properties[key]=value.slice(0,240);
        else if(typeof value==='number'||typeof value==='boolean')properties[key]=value;
      }
      const id=String(feature.id??properties.id??properties.name??'poi')+'|'+lng.toFixed(6)+'|'+lat.toFixed(6);
      if(seen.has(id))continue;seen.add(id);
      features.push({type:'Feature',id,geometry:{type:'Point',coordinates:[lng,lat]},properties});
      if(features.length>=1500)break;
    }
    if(features.length>=1500)break;
  }
  return {type:'FeatureCollection',features,bbox:[bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()],
    zoom:map.getZoom(),captured_at:new Date().toISOString(),source:'System Points of Interest — loaded basemap vector tiles'};
}
