import json
from fastapi import APIRouter, HTTPException

from app.services.simulation.planning import system_demo

router = APIRouter(prefix="/api/v1/planning/demo/system", tags=["planning-test-demo"])


def require_demo():
    if not system_demo.enabled():
        raise HTTPException(404, "System integration is enabled only in the test demo")


@router.get("/snapshots")
def snapshots():
    require_demo()
    items = []
    for path in sorted(system_demo.directory().glob("*.json")):
        try:
            doc = system_demo.load(path.stem)
            items.append({"id": path.stem, "captured_at": doc["captured_at"], "bbox": doc["bbox"],
                          "parcel_count": len(system_demo.candidates(doc)),
                          "population": doc.get("population", {}).get("statistics", {}).get("population_sum"),
                          "source": "Installed read-only team API + OSM snapshot"})
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            continue
    return {"demo_only": True, "snapshots": items}


@router.get('/counting-references')
def counting_references():
    require_demo()
    from app.services.simulation.planning.counting_reference import directory,load
    items=[]
    for path in sorted(directory().glob('*.json')):
        try:
            doc=load(path.stem)
            items.append({'id':path.stem,'camera_id':doc['camera_id'],'counts':doc['counts'],
                'duration_seconds':doc['observation']['duration_seconds'],'simulation_ready':False,
                'use':'Uncalibrated vehicle-mix or transferred flow default; not current site OD'})
        except (ValueError,KeyError,OSError):
            continue
    return {'demo_only':True,'references':items}


@router.get('/traffic-default')
def traffic_default():
    require_demo()
    from app.services.simulation.planning.counting_reference import default_identifier, flow_default
    identifier=default_identifier()
    if identifier is None:
        raise HTTPException(404,'No default counting reference is installed')
    try:
        return {'demo_only':True,**flow_default(identifier)}
    except (ValueError,OSError) as error:
        raise HTTPException(422,str(error)) from None


@router.get("/snapshots/{identifier}/parcels")
def parcels(identifier: str):
    require_demo()
    try:
        doc = system_demo.load(identifier)
        return {"type": "FeatureCollection", "features": system_demo.candidates(doc),
                "snapshot_id": identifier, "captured_at": doc["captured_at"], "demo_only": True}
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from None


@router.post("/prepare")
def prepare(body: system_demo.Prepare):
    require_demo()
    try:
        return {"demo_only": True, "study": system_demo.prepare(body)}
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from None


@router.get("/vietnam-catalog")
def vietnam_catalog():
    require_demo()
    from app.services.simulation.planning.vietnam_rules import catalog
    return catalog()
