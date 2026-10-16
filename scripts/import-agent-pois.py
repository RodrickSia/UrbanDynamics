"""Prepare a bounded, provenance-preserving local OSM POI snapshot. Requires osmium."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

import osmium

BASE='https://download.bbbike.org/osm/bbbike/Saigon/'
CATEGORIES={'supermarket':('shop','supermarket'),'park':('leisure','park'),'hospital':('amenity','hospital')}


def download(name,target):
    request=Request(BASE+name,headers={'User-Agent':'UrbanDynamics/2026 (https://github.com/RodrickSia/UrbanDynamics)'})
    with urlopen(request,timeout=60) as response,target.open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
        return response.headers.get('Last-Modified')


class Amenities(osmium.SimpleHandler):
    def __init__(self):
        super().__init__();self.features=[]

    def add(self,item,kind,coords):
        tags=dict(item.tags)
        category=next((c for c,(k,v) in CATEGORIES.items() if tags.get(k)==v),None)
        if not category or not coords:return
        closed=len(coords)>=4 and coords[0]==coords[-1]
        geometry={'type':'Polygon','coordinates':[coords]} if closed else {'type':'Point','coordinates':coords[0]}
        self.features.append({'type':'Feature','id':f'{kind}/{item.id}','geometry':geometry,
                              'properties':{**tags,'category':category}})

    def node(self,node):
        if node.location.valid():self.add(node,'node',[[node.location.lon,node.location.lat]])

    def way(self,way):
        if not any(way.tags.get(k)==v for k,v in CATEGORIES.values()):return
        try:self.add(way,'way',[[node.lon,node.lat] for node in way.nodes])
        except osmium.InvalidLocationError:pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=args.output_dir;root.mkdir(parents=True,exist_ok=True)
    pbf=root/'Saigon.osm.pbf'
    modified=download('Saigon.osm.pbf',pbf)
    download('CHECKSUM.txt',root/'CHECKSUM.txt');download('Saigon.poly',root/'Saigon.poly')
    expected=next(line.split()[0] for line in (root/'CHECKSUM.txt').read_text().splitlines() if line.endswith(' Saigon.osm.pbf'))
    content=pbf.read_bytes()
    if hashlib.md5(content).hexdigest()!=expected:raise ValueError('Published PBF checksum mismatch; retry a consistent source snapshot')
    # This provider publishes one rectangular polygon; reject a changed format
    # rather than pretending an arbitrary bbox establishes coverage.
    lines=(root/'Saigon.poly').read_text().strip().splitlines()
    if lines[1].strip()!='1' or [line.strip() for line in lines[-2:]]!=['END','END']:
        raise ValueError('Unexpected BBBike polygon format')
    ring=[[float(x) for x in line.split()] for line in lines[2:-2]]
    if any(len(point)!=2 for point in ring):raise ValueError('Invalid coverage polygon')
    if ring[-1]!=ring[0]:ring.append(ring[0])
    handler=Amenities();handler.apply_file(str(pbf),locations=True,idx='flex_mem')
    document={'schema_version':1,'source':'OpenStreetMap via BBBike Saigon PBF extract',
        'source_url':BASE+'Saigon.osm.pbf','source_last_modified':modified,
        'captured_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(content).hexdigest(),
        'published_md5_verified':expected,'attribution':'© OpenStreetMap contributors / BBBike extract',
        'license':'ODbL','coverage_geometry':{'type':'Polygon','coordinates':[ring]},
        'coverage':'Source extract extent only; mapped POI completeness and operating status unverified. Nodes and ways imported; relation-only POIs not assembled.',
        'category_counts':dict(Counter(f['properties']['category'] for f in handler.features)),
        'features':handler.features}
    output=root/'offline-bbbike-saigon.json';temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8');temporary.replace(output)
    print(json.dumps({k:v for k,v in document.items() if k not in ('features',)},ensure_ascii=False))


if __name__=='__main__':main()
