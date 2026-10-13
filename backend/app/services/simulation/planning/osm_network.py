"""Common OSM public graph, hypothetical parcel accesses and explicit OD prior."""
import hashlib
import math
import os
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

from shapely.geometry import LineString, mapping, shape

from ..integrated.road_network import write_osm, route_between
from .parcels import registry
from .runner import execute
from .system_demo import load


def source_specification(study):
    document=load(study.system_snapshot_id)
    features=[]
    region=shape(study.study_area.model_dump())
    for way in document.get('osm',{}).get('elements',[]):
        if way.get('type')!='way' or not way.get('tags',{}).get('highway') or len(way.get('geometry',[]))<2:
            continue
        line=LineString([(p['lon'],p['lat']) for p in way['geometry']]).intersection(region)
        if line.is_empty:
            continue
        features.append({'type':'Feature','geometry':mapping(line),
            'properties':{'osm_way_id':way['id'],'source_kind':'osm_topology','tags':way['tags']}})
    if not features:
        raise ValueError('Installed snapshot has no OSM roads for planning traffic')
    return {'nodes':[], 'edges':features, 'map':{'type':'FeatureCollection','features':features},
        'source_snapshot_id':study.system_snapshot_id,
        'provenance':{'kind':'osm_topology_with_estimated_demand',
            'edge_count_basis':'source OSM ways, not imported directed SUMO edges',
            'access_method':'nearest connected public junction, within 500 m, hypothetical',
            'signal_method':'OSM signal tags; netconvert phases, not measured',
            'od_method':'reachable outer approaches grouped in eight sectors, equal-route prior; no camera fit'}}


def build(study,directory,checkpoint=None):
    import sumo
    tools_path=str(Path(sumo.SUMO_HOME)/'tools')
    if tools_path not in sys.path:
        sys.path.append(tools_path)
    import sumolib
    suffix='.exe' if os.name=='nt' else ''
    binaries=Path(sumo.SUMO_HOME)/'bin';netconvert=str(binaries/('netconvert'+suffix))
    def run(args):
        execute(args,directory,checkpoint)
    document=load(study.system_snapshot_id)
    write_osm(document['osm'],directory/'source.osm.xml')
    bbox=shape(study.study_area.model_dump()).bounds
    run([netconvert,'--osm-files','source.osm.xml','--output-file','public.xml',
         '--keep-edges.by-vclass','passenger,motorcycle','--keep-edges.in-geo-boundary',','.join(map(str,bbox)),
         '--geometry.remove','true','--no-turnarounds','true'])
    public=sumolib.net.readNet(str(directory/'public.xml'))
    public_edges=[e for e in public.getEdges() if e.allows('passenger') and e.allows('motorcycle') and e.getLength()>=20]
    if not 4<=len(public_edges)<=4000:
        raise ValueError('OSM pilot requires 4–4000 drivable edges')
    physical=registry(study)
    projects=sorted(study.projects,key=lambda p:p.id)
    geometry_keys={p.id:shape(p.site.model_dump()).normalize().wkb_hex for p in projects}
    solver_ids={p.id:'p_'+hashlib.sha256(geometry_keys[p.id].encode()).hexdigest()[:24] for p in projects}
    nodes,edges,connections=ET.Element('nodes'),ET.Element('edges'),ET.Element('connections')
    accesses={}
    eligible=[n for n in public.getNodes() if any(e in public_edges for e in n.getIncoming()) and any(e in public_edges for e in n.getOutgoing())]
    for p in projects:
        if physical[p.id]!=p.id:
            continue
        centroid=shape(p.site.model_dump()).representative_point()
        xy=public.convertLonLat2XY(centroid.x,centroid.y)
        near=sorted(eligible,key=lambda n:(math.dist(n.getCoord(),xy),n.getID()))
        nearest=next((n for n in near if 5<=math.dist(n.getCoord(),xy)<=500),None)
        if nearest is None:
            raise ValueError('No connected OSM access within 5–500 m for project '+p.id)
        identifier=solver_ids[p.id];gate=identifier+'_gate'
        ET.SubElement(nodes,'node',id=gate,x=str(xy[0]),y=str(xy[1]))
        for direction,a,b in [('in',nearest.getID(),gate),('out',gate,nearest.getID())]:
            ET.SubElement(edges,'edge',id=identifier+'_'+direction,**{'from':a,'to':b,'speed':'8.33',
                'numLanes':str(p.development.gate_lanes),'allow':'passenger motorcycle','priority':'1'})
        for incoming in nearest.getIncoming():
            if incoming.allows('passenger') and incoming.allows('motorcycle'):
                ET.SubElement(connections,'connection',**{'from':incoming.getID(),'to':identifier+'_in','fromLane':'0','toLane':'0'})
        accesses[identifier]={'project_id':p.id,'junction_id':nearest.getID(),'length_m':math.dist(nearest.getCoord(),xy),
            'kind':'hypothetical_nearest_junction_access'}
    for name,root in [('access.nodes.xml',nodes),('access.edges.xml',edges),('access.connections.xml',connections)]:
        ET.ElementTree(root).write(directory/name,encoding='utf-8',xml_declaration=True)
    run([netconvert,'--sumo-net-file','public.xml','--node-files','access.nodes.xml','--edge-files','access.edges.xml',
        '--connection-files','access.connections.xml','--output-file','network.xml','--no-turnarounds','true'])
    network=sumolib.net.readNet(str(directory/'network.xml'))
    private={identifier+'_'+direction for identifier in accesses for direction in ('in','out')}
    public_edges=[e for e in network.getEdges() if e.getID() not in private and e.allows('passenger') and e.allows('motorcycle')]
    def reached(edge,reverse=False):
        seen={edge.getID()};pending=[edge]
        while pending:
            item=pending.pop()
            for neighbor in (item.getIncoming() if reverse else item.getOutgoing()):
                if neighbor.getID() not in seen and neighbor.allows('passenger') and neighbor.allows('motorcycle'):
                    seen.add(neighbor.getID());pending.append(neighbor)
        return seen
    def approaches(allowed,xy):
        sectors={}
        for edge in sorted(public_edges,key=lambda e:e.getID()):
            if edge.getID() not in allowed:
                continue
            a,b=edge.getFromNode().getCoord(),edge.getToNode().getCoord();point=((a[0]+b[0])/2,(a[1]+b[1])/2)
            angle=int((math.atan2(point[1]-xy[1],point[0]-xy[0])+math.pi)/(2*math.pi)*8)%8
            score=math.dist(point,xy)
            if angle not in sectors or score>sectors[angle][0]:
                sectors[angle]=(score,edge)
        return [edge for _,edge in [sectors[k] for k in sorted(sectors)]]
    routes={};project_routes={};background={}
    for identifier in sorted(accesses):
        center=network.getEdge(identifier+'_in').getToNode().getCoord()
        origins=approaches(reached(network.getEdge(identifier+'_in'),True),center)
        destinations=approaches(reached(network.getEdge(identifier+'_out')),center)
        groups={'in':[],'out':[]}
        for direction,candidates in [('in',origins),('out',destinations)]:
            for edge in candidates:
                start,end=(edge,network.getEdge(identifier+'_in')) if direction=='in' else (network.getEdge(identifier+'_out'),edge)
                path=route_between(network,start,end)
                if path and not any(token in private for token in path.split() if token not in (identifier+'_'+direction,)):
                    rid=identifier+'_'+direction+'_'+str(len(groups[direction]));routes[rid]=path.split();groups[direction].append(rid)
        if any(not group for group in groups.values()):
            raise ValueError('No routable OSM boundary/access pair for '+identifier)
        project_routes[identifier]=[rid for i in range(math.lcm(len(groups['in']),len(groups['out'])))
            for rid in (groups['in'][i%len(groups['in'])],groups['out'][i%len(groups['out'])])]
        for a in origins:
            for b in destinations:
                if a==b:
                    continue
                path=route_between(network,a,b)
                if path and not any(token in private for token in path.split()):
                    background.setdefault(tuple(path.split()),path.split())
    if not background:
        raise ValueError('No public-only OSM background routes; do not substitute generated corridor')
    background_routes=[]
    for i,path in enumerate(sorted(background.values())):
        rid='background_'+str(i);routes[rid]=path;background_routes.append(rid)
    features=[]
    for edge in sorted(network.getEdges(),key=lambda e:e.getID()):
        if not edge.allows('passenger') or not edge.allows('motorcycle'):
            continue
        connector=edge.getID() in private
        props={'edge_id':edge.getID(),'source_kind':'synthetic_access' if connector else 'osm_topology',
            'private':connector,'lanes':len(edge.getLanes()),'speed_m_s':edge.getSpeed()}
        if connector:
            props['project_ids']=[p.id for p in projects if edge.getID().startswith(solver_ids[p.id]+'_')]
        features.append({'type':'Feature','geometry':{'type':'LineString','coordinates':[network.convertXY2LonLat(*xy) for xy in edge.getShape()]},'properties':props})
    return {'directory':str(directory),'binary':str(binaries/('sumo'+suffix)), 'routes':routes,
        'map':{'type':'FeatureCollection','features':features},'background_routes':background_routes,'project_routes':project_routes,
        'project_to_physical_parcel':physical,'project_to_solver_parcel':solver_ids,
        'project_random_keys':{p.id:hashlib.sha256(geometry_keys[p.id].encode()).hexdigest() for p in projects},
        'provenance':{'kind':'osm_topology_with_estimated_demand','source_snapshot_id':study.system_snapshot_id,
            'directed_edges':len(features),'accesses':accesses,'background_can_use_private_access':False,
            'od_method':'equal allocation across reachable outer-approach routes; not observed OD',
            'signal_method':'OSM signal tags where present; netconvert generated phase timings',
            'baseline_basis':'All hypothetical access roads exist in every scenario; inactive accesses have no project trips'}}
