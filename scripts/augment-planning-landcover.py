"""Add bounded source WorldCover to an immutable existing demo snapshot."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'etl')]
from app.services.simulation.integrated.background import publish
from app.services.simulation.integrated.landcover import fetch

folder=ROOT/'.runtime/planning-system/snapshots'
snapshots=[(json.loads(p.read_text(encoding='utf-8')),p.stem) for p in folder.glob('*.json')]
document,identifier=max(snapshots,key=lambda item:item[0]['captured_at'])
if document.get('landcover'):
    print('Latest snapshot already includes landcover: '+identifier)
else:
    document['derived_from_snapshot_id']=identifier
    document['base_snapshot_captured_at']=document['captured_at']
    document['landcover']=fetch(document['bbox'])
    document['sources']['landcover']=document['landcover']['metadata']
    document.get('failures',{}).pop('landcover',None)
    document['captured_at']=datetime.now(timezone.utc).isoformat()
    current=publish(document,folder)
    report={'status':'passed','snapshot_id':current,'derived_from_snapshot_id':identifier,
            'landcover_features':len(document['landcover']['features']),'metadata':document['landcover']['metadata']}
    path=ROOT/'test-results/planning-system-osm-counting/landcover-acquisition.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
